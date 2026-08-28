from contextlib import closing
from decimal import Decimal
import json
import pyodbc
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from ..parameter_labels import PARAMETER_LABELS, EXCLUDED_FROM_TARGETS, categorize_tag
from ..database import get_connection, row_to_dict
from ..parameter_labels import PARAMETER_LABELS, categorize_tag
from ..schemas import FavoriteCreateRequest
from ..security import require_editor, require_user


router = APIRouter(prefix="/api", tags=["favorites"])


def _json_safe(value):
    """pyodbc returns numeric columns as Decimal, which json.dumps()
    cannot serialize on its own (raises TypeError -> uncaught -> bare 500,
    since it's not a pyodbc.Error). Normalize whole-number Decimals to
    int (so a reading of 25 is stored/serialized as "25", not "25.0") and
    only fall back to float for values that actually have a fractional
    part. Storing "25.0" here is what made a hand-typed "25" schematic
    value compare as different from an otherwise-identical device
    reading -- see _values_equal below for the other half of the fix."""
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def _values_equal(a, b) -> bool:
    """True if two saved parameter values represent the same value,
    regardless of which pipeline produced their string/number form (a
    live device reading normalized by _json_safe, a hand-typed 高级工艺
    参数 value, or a value round-tripped through JSON). Falls back to
    plain equality for anything that doesn't parse as a number, so
    non-numeric/enum values (e.g. mode codes as text) still compare
    exactly as before."""
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def _snapshot_value_map(parameters: list[dict]) -> dict:
    """Reduces a parameters snapshot (parameter_id/label/category/value)
    down to just {parameter_id: value}, so two snapshots can be compared
    for meaningful equality regardless of list order or the (derived,
    always-identical-for-a-given-tag) label/category fields."""
    return {p.get("parameter_id"): p.get("value") for p in parameters}


def _snapshot_maps_equal(a: dict, b: dict) -> bool:
    """Numeric-aware comparison of two {parameter_id: value} maps (see
    _values_equal) -- replaces a plain dict `==` comparison, which failed
    whenever one side's numeric value had a ".0" suffix and the other
    didn't (same number, different string form)."""
    if a.keys() != b.keys():
        return False
    return all(_values_equal(a[key], b[key]) for key in a)

def _snapshot_value_map(parameters: list[dict]) -> dict:
    """Reduces a parameters snapshot (parameter_id/label/category/value)
    down to just {parameter_id: value}, so two snapshots can be compared
    for meaningful equality regardless of list order or the (derived,
    always-identical-for-a-given-tag) label/category fields."""
    return {p.get("parameter_id"): p.get("value") for p in parameters}


def _build_parameters_snapshot(cursor, device_id: str, raw_message_id: int) -> list[dict]:
    """Same decorated shape GET /api/tech/{device_id} returns, but pinned
    to one specific raw_message_id instead of "latest" -- this is what
    lets a favorite freeze the exact reading behind a 变更记录 row rather
    than whatever the device is reporting right now."""
    cursor.execute(
        """
        SELECT parameter_id, parameter_value_text, parameter_value
        FROM dbo.vw_machine_tech
        WHERE device_id = ? AND raw_message_id = ?
        ORDER BY parameter_id
        """,
        device_id,
        raw_message_id,
    )
    rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="该时间点没有找到工艺参数数据")

    parameters = []
    for row in rows:
        tag_id = row.parameter_id
        value = row.parameter_value if row.parameter_value is not None else row.parameter_value_text
        value = _json_safe(value)
        meta = PARAMETER_LABELS.get(tag_id)
        if meta is None:
            parameters.append(
                {"parameter_id": tag_id, "label": tag_id, "category": "未知参数", "value": value}
            )
            continue
        if not meta["use"]:
            continue
        parameters.append(
            {
                "parameter_id": tag_id,
                "label": meta["label"],
                "category": categorize_tag(tag_id, meta["label"]),
                "value": value,
            }
        )
    return parameters

def _build_schematic_snapshot_from_targets(cursor, machine_type_id: int) -> list[dict] | None:
    """Same shape as _build_parameters_snapshot (parameter_id/label/
    category/value), but reads the *current* dbo.mold_parameter_targets
    rows for a machine type instead of a live device reading -- used to
    back up the existing 高级工艺参数 schematic before a favorite
    overwrites it. Returns None if there's nothing worth backing up (no
    rows, or every target_value is blank)."""
    cursor.execute(
        "SELECT parameter_id, target_value FROM dbo.mold_parameter_targets WHERE machine_type_id = ?",
        machine_type_id,
    )
    rows = [(r.parameter_id, r.target_value) for r in cursor.fetchall() if r.target_value not in (None, "")]
    if not rows:
        return None

    parameters = []
    for tag_id, value in rows:
        meta = PARAMETER_LABELS.get(tag_id)
        if meta is None:
            parameters.append({"parameter_id": tag_id, "label": tag_id, "category": "未知参数", "value": value})
            continue
        parameters.append({
            "parameter_id": tag_id,
            "label": meta["label"],
            "category": categorize_tag(tag_id, meta["label"]),
            "value": value,
        })
    return parameters


def _unique_backup_name(cursor, machine_type_id: int, base_name: str) -> str:
    """Appends a numeric suffix if base_name already exists for this
    machine type -- (machine_type_id, name) is unique (see
    setup_favorites.sql), and two backups saved within the same minute
    would otherwise collide."""
    name = base_name
    suffix = 2
    while cursor.execute(
        "SELECT 1 FROM dbo.mold_favorite_snapshots WHERE machine_type_id = ? AND name = ?",
        machine_type_id, name,
    ).fetchone():
        name = f"{base_name} ({suffix})"
        suffix += 1
    return name


@router.post("/molds/{mold_id}/machine-types/{machine_type_id}/favorites/{favorite_id}/apply")
def apply_favorite_to_schematic(
    mold_id: int,
    machine_type_id: int,
    favorite_id: int,
    user: dict = Depends(require_user),
):
    """Overwrites this machine type's 高级工艺参数 schematic
    (dbo.mold_parameter_targets) with the value snapshot saved in a
    favorite. If the schematic currently holds any values, they're saved
    first as a new, dated favorite -- so applying a saved recipe is never
    destructive.

    Only target_value is replaced from the favorite; tolerance_mode /
    tolerance_percent / tolerance_flat for a tag are carried over
    unchanged if that tag already had a target row (so tolerance settings
    survive switching between saved recipes), and default to percent /
    no-tolerance for a tag that had none.
    """
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()

            machine_type = _get_machine_type_or_404(cursor, machine_type_id)
            if machine_type.mold_id != mold_id:
                raise HTTPException(status_code=404, detail="机型不属于该模具")

            favorite_row = cursor.execute(
                "SELECT id, machine_type_id, parameters_json FROM dbo.mold_favorite_snapshots WHERE id = ?",
                favorite_id,
            ).fetchone()
            if favorite_row is None:
                raise HTTPException(status_code=404, detail="收藏不存在")
            if favorite_row.machine_type_id != machine_type_id:
                raise HTTPException(status_code=400, detail="该收藏不属于当前机型")

            # ---- back up the current schematic first, if it has anything ----
            backup_snapshot = _build_schematic_snapshot_from_targets(cursor, machine_type_id)
            if backup_snapshot is not None:
                backup_name = _unique_backup_name(
                    cursor, machine_type_id,
                    f"自动备份 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                )
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_favorite_snapshots
                        (machine_type_id, name, device_id, captured_data_time, parameters_json, created_by, is_backup)
                    VALUES (?, ?, N'', SYSUTCDATETIME(), ?, ?, 1)
                    """,
                    machine_type_id,
                    backup_name,
                    json.dumps(backup_snapshot, ensure_ascii=False, default=str),
                    user["id"],
                )

            # ---- apply the favorite's values onto the live schematic ----
            valid_tags = set(PARAMETER_LABELS.keys()) - EXCLUDED_FROM_TARGETS
            existing = {
                row.parameter_id: row
                for row in cursor.execute(
                    "SELECT parameter_id, tolerance_mode, tolerance_percent, tolerance_flat "
                    "FROM dbo.mold_parameter_targets WHERE machine_type_id = ?",
                    machine_type_id,
                ).fetchall()
            }
            cursor.execute("DELETE FROM dbo.mold_parameter_targets WHERE machine_type_id = ?", machine_type_id)

            for item in json.loads(favorite_row.parameters_json):
                tag = item.get("parameter_id")
                value = item.get("value")
                if tag not in valid_tags or value in (None, ""):
                    continue
                prior = existing.get(tag)
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_parameter_targets
                        (mold_id, machine_type_id, parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat)
                    VALUES (NULL, ?, ?, ?, ?, ?, ?)
                    """,
                    machine_type_id,
                    tag,
                    str(value),
                    prior.tolerance_mode if prior else "percent",
                    prior.tolerance_percent if prior else None,
                    prior.tolerance_flat if prior else None,
                )

            connection.commit()
            return {"status": "ok", "backed_up": backup_snapshot is not None}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


def _get_machine_type_or_404(cursor, machine_type_id: int):
    row = cursor.execute(
        "SELECT id, mold_id, machine_type FROM dbo.mold_machine_types WHERE id = ?",
        machine_type_id,
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="机型不存在")
    return row


@router.post("/changelog/{changelog_id}/favorite", status_code=201)
def create_favorite_from_changelog(
    changelog_id: int,
    data: FavoriteCreateRequest,
    user: dict = Depends(require_user),
):
    """Snapshot every 工艺参数 tag as it stood at the moment of a
    specific 变更记录 row, and save it against a Mold + Machine Type.

    If a favorite with this name already exists for the machine type:
      - If its saved values are identical to the new snapshot, nothing is
        written -- the response comes back with unchanged=True so the
        frontend can tell the user "这与已保存的版本相同" instead of
        writing a pointless duplicate/backup.
      - Otherwise, without overwrite=True, this 409s exactly as before so
        the frontend can confirm with the user.
      - With overwrite=True (and the content actually differs), the
        *old* version is preserved as an auto-backup (is_backup=1, same
        convention as apply_favorite_to_schematic) before the named
        favorite's row is updated in place -- so overwriting a favorite
        is never destructive, just like applying one.
    """
    require_editor(user)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请输入收藏名称")

    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()

            changelog_row = cursor.execute(
                "SELECT device_id, raw_message_id, data_time FROM dbo.tech_parameter_changelog WHERE id = ?",
                changelog_id,
            ).fetchone()
            if changelog_row is None:
                raise HTTPException(status_code=404, detail="变更记录不存在")

            _get_machine_type_or_404(cursor, data.machine_type_id)

            parameters = _build_parameters_snapshot(
                cursor, changelog_row.device_id, changelog_row.raw_message_id
            )
            # default=str as a last-resort safety net for any other
            # non-JSON-native type (e.g. datetime) that might slip through.
            payload = json.dumps(parameters, ensure_ascii=False, default=str)

            existing = cursor.execute(
                "SELECT id, parameters_json FROM dbo.mold_favorite_snapshots WHERE machine_type_id = ? AND name = ?",
                data.machine_type_id, name,
            ).fetchone()

            if existing is not None:
                existing_values = _snapshot_value_map(json.loads(existing.parameters_json))
                new_values = _snapshot_value_map(parameters)
                if _snapshot_maps_equal(existing_values, new_values):
                    return {
                        "status": "ok",
                        "unchanged": True,
                        "id": existing.id,
                        "message": f"「{name}」的内容与当前保存的版本相同，未作修改",
                    }

            if existing and not data.overwrite:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "favorite_name_exists",
                        "message": f"该机型下已存在名为「{name}」的收藏，是否覆盖？",
                    },
                )

            if existing:
                # ---- preserve the version being replaced as a backup ----
                backup_name = _unique_backup_name(
                    cursor, data.machine_type_id,
                    f"{name} 自动备份 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                )
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_favorite_snapshots
                        (machine_type_id, name, device_id, source_raw_message_id, source_changelog_id,
                         captured_data_time, parameters_json, created_by, is_backup)
                    SELECT machine_type_id, ?, device_id, source_raw_message_id, source_changelog_id,
                           captured_data_time, parameters_json, created_by, 1
                    FROM dbo.mold_favorite_snapshots
                    WHERE id = ?
                    """,
                    backup_name,
                    existing.id,
                )

                cursor.execute(
                    """
                    UPDATE dbo.mold_favorite_snapshots
                    SET device_id = ?, source_raw_message_id = ?, source_changelog_id = ?,
                        captured_data_time = ?, parameters_json = ?,
                        updated_at = SYSUTCDATETIME(), updated_by = ?
                    WHERE id = ?
                    """,
                    changelog_row.device_id,
                    changelog_row.raw_message_id,
                    changelog_id,
                    changelog_row.data_time,
                    payload,
                    user["id"],
                    existing.id,
                )
                favorite_id = existing.id
            else:
                favorite_id = cursor.execute(
                    """
                    INSERT INTO dbo.mold_favorite_snapshots
                        (machine_type_id, name, device_id, source_raw_message_id,
                         source_changelog_id, captured_data_time, parameters_json, created_by)
                    OUTPUT INSERTED.id
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    data.machine_type_id,
                    name,
                    changelog_row.device_id,
                    changelog_row.raw_message_id,
                    changelog_id,
                    changelog_row.data_time,
                    payload,
                    user["id"],
                ).fetchone()[0]

            connection.commit()
            return {"status": "ok", "id": favorite_id}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/molds/{mold_id}/machine-types/{machine_type_id}/favorites")
def list_favorites(mold_id: int, machine_type_id: int, user: dict = Depends(require_user)):
    """Named favorites first (newest first), then auto-backups (also
    newest first) -- see setup_favorites_backup_flag.sql, which added
    is_backup plus IX_mold_favorite_snapshots_backup_order specifically
    for this ordering. Previously this query selected neither is_backup
    nor ordered by it, so despite the frontend already grouping/
    dividing the list on that assumption (see favoriteListRowHtml /
    refreshFavoritesList in app.js), backups and named favorites were
    actually interleaved by updated_at alone."""
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            machine_type = _get_machine_type_or_404(cursor, machine_type_id)
            if machine_type.mold_id != mold_id:
                raise HTTPException(status_code=404, detail="机型不属于该模具")
            cursor.execute(
                """
                SELECT id, name, device_id, captured_data_time, updated_at, is_backup
                FROM dbo.mold_favorite_snapshots
                WHERE machine_type_id = ?
                ORDER BY is_backup ASC, updated_at DESC
                """,
                machine_type_id,
            )
            return [row_to_dict(cursor, row) for row in cursor.fetchall()]
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/favorites/{favorite_id}")
def get_favorite(favorite_id: int, user: dict = Depends(require_user)):
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            row = cursor.execute(
                """
                SELECT id, machine_type_id, name, device_id, captured_data_time,
                       parameters_json, updated_at
                FROM dbo.mold_favorite_snapshots
                WHERE id = ?
                """,
                favorite_id,
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="收藏不存在")
            record = row_to_dict(cursor, row)
            record["parameters"] = json.loads(record.pop("parameters_json"))
            return record
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.delete("/favorites/{favorite_id}")
def delete_favorite(favorite_id: int, user: dict = Depends(require_user)):
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM dbo.mold_favorite_snapshots WHERE id = ?", favorite_id)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="收藏不存在")
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error