from contextlib import closing
from datetime import datetime

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_connection, row_to_dict
from ..parameter_labels import PARAMETER_LABELS, base_name, categorize
from ..security import require_user


router = APIRouter(prefix="/api", tags=["changelog"])


def _decorate(record: dict) -> dict:
    """Attach the human-readable label/category the frontend needs, using
    the same PARAMETER_LABELS dictionary the 工艺参数 tab is built from."""
    meta = PARAMETER_LABELS.get(record["parameter_id"])
    record["label"] = meta["label"] if meta else record["parameter_id"]
    record["category"] = categorize(record["label"])
    return record


def _tags_for(field: str | None, sub: str | None) -> list[str] | None:
    """Resolve a (field, sub) filter selection to the list of raw tag codes
    it covers. Returns None when no filter was requested (no WHERE clause
    needed), or a (possibly empty) list of tags otherwise."""
    if not field and not sub:
        return None
    tags = []
    for tag, meta in PARAMETER_LABELS.items():
        if not meta["use"]:
            continue
        if field and categorize(meta["label"]) != field:
            continue
        if sub and base_name(meta["label"]) != sub:
            continue
        tags.append(tag)
    return tags


def _parse_date(date: str | None):
    if not date:
        return None
    try:
        return datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD") from None


def _build_where(date_value, tags: list[str] | None, mold: str | None = None) -> tuple[str, list]:
    conditions = []
    params: list = []
    if date_value is not None:
        conditions.append("CAST(COALESCE(c.data_time, c.detected_at) AS DATE) = ?")
        params.append(date_value)
    if tags is not None:
        if not tags:
            # A field/sub combination that matched nothing real -- force
            # an empty result instead of accidentally returning everything.
            conditions.append("1 = 0")
        else:
            placeholders = ",".join("?" for _ in tags)
            conditions.append(f"c.parameter_id IN ({placeholders})")
            params.extend(tags)
    if mold:
        # Matches this row's own 收藏 records (see favorited_to below) --
        # only non-backup favorites count as a deliberate "favorited to
        # this mold" association.
        conditions.append(
            """EXISTS (
                SELECT 1
                FROM dbo.mold_favorite_snapshots AS f
                INNER JOIN dbo.mold_machine_types AS mt ON mt.id = f.machine_type_id
                INNER JOIN dbo.molds AS m ON m.id = mt.mold_id
                WHERE f.source_changelog_id = c.id AND f.is_backup = 0
                  AND (m.mold_code LIKE ? OR m.mold_name LIKE ?)
            )"""
        )
        like = f"%{mold}%"
        params.extend([like, like])
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params


# Every changelog SELECT joins in dbo.vw_machine_spc so we can show the
# operator-facing 模数 (CYCN / cycle_number) instead of the raw internal
# spc_message_id. The join key is unchanged: spc_message_id still points at
# dbo.mqtt_messages.id, we're just resolving it to a friendlier display
# value via the same view GET /api/spc/{device_id} already reads from.
CHANGELOG_SELECT = """
    c.id, c.device_id, c.parameter_id, c.previous_value, c.new_value,
    c.data_time, c.detected_at, c.raw_message_id, c.spc_message_id,
    s.cycle_number AS spc_cycle_number,
    fav.favorited_to
"""
CHANGELOG_FROM = """
    FROM dbo.tech_parameter_changelog AS c
    LEFT JOIN dbo.vw_machine_spc AS s ON s.raw_message_id = c.spc_message_id
    CROSS APPLY (
        -- Every mold this changelog row has been saved as a favorite
        -- against (dbo.mold_favorite_snapshots.source_changelog_id ->
        -- machine_type -> mold), deduplicated by mold and comma-joined
        -- (a row can be favorited under more than one machine type of the
        -- same mold). Backups (is_backup=1, created automatically when a
        -- favorite is overwritten/applied -- see favorites.py) are
        -- excluded, since those aren't a deliberate "favorited to this
        -- mold" action by the user. NULL when this row was never
        -- favorited.
        SELECT STRING_AGG(x.mold_code, N', ') WITHIN GROUP (ORDER BY x.mold_code) AS favorited_to
        FROM (
            SELECT DISTINCT m2.mold_code
            FROM dbo.mold_favorite_snapshots AS f
            INNER JOIN dbo.mold_machine_types AS mt2 ON mt2.id = f.machine_type_id
            INNER JOIN dbo.molds AS m2 ON m2.id = mt2.mold_id
            WHERE f.source_changelog_id = c.id AND f.is_backup = 0
        ) AS x
    ) AS fav
"""


@router.get("/changelog/filters")
def get_changelog_filters(user: dict = Depends(require_user)):
    """Field -> sub-field -> [parameter_id...] tree used to populate the
    cascading 变更记录 filter dropdowns on the frontend."""
    del user
    tree: dict[str, dict[str, list[str]]] = {}
    for tag, meta in PARAMETER_LABELS.items():
        if not meta["use"]:
            continue
        field = categorize(meta["label"])
        sub = base_name(meta["label"])
        tree.setdefault(field, {}).setdefault(sub, []).append(tag)
    return tree


@router.get("/changelog")
def get_changelog(
    date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    field: str | None = Query(None),
    sub: str | None = Query(None),
    mold: str | None = Query(None),
    device_id: str | None = Query(None, description="Filter to a single device_id, same as the per-device changelog tab."),
    user: dict = Depends(require_user),
):
    del user
    date_value = _parse_date(date)
    tags = _tags_for(field, sub)
    where_clause, params = _build_where(date_value, tags, mold)
    if device_id:
        device_condition = "c.device_id LIKE ?"
        where_clause = f"{where_clause} AND {device_condition}" if where_clause else f"WHERE {device_condition}"
        params = params + [f"%{device_id}%"]
    sql = f"""
        SELECT TOP 500
            {CHANGELOG_SELECT}
        {CHANGELOG_FROM}
        {where_clause}
        ORDER BY c.detected_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params) if params else cursor.execute(sql)
            return [_decorate(row_to_dict(cursor, row)) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/changelog/by-device/{device_id}")
def get_changelog_for_device(
    device_id: str,
    date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    field: str | None = Query(None),
    sub: str | None = Query(None),
    mold: str | None = Query(None),
    user: dict = Depends(require_user),
):
    """Same records as GET /api/changelog, filtered to one machine (and
    optionally by date/field/sub/mold) -- powers the 变更记录 tab inside the
    device detail view."""
    del user
    date_value = _parse_date(date)
    tags = _tags_for(field, sub)
    where_clause, params = _build_where(date_value, tags, mold)
    device_condition = "c.device_id = ?"
    where_clause = f"{where_clause} AND {device_condition}" if where_clause else f"WHERE {device_condition}"
    params = params + [device_id]
    sql = f"""
        SELECT TOP 200
            {CHANGELOG_SELECT}
        {CHANGELOG_FROM}
        {where_clause}
        ORDER BY c.detected_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            return [_decorate(row_to_dict(cursor, row)) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/changelog/{changelog_id}")
def get_changelog_entry(changelog_id: int, user: dict = Depends(require_user)):
    del user
    sql = f"""
        SELECT
            {CHANGELOG_SELECT}
        {CHANGELOG_FROM}
        WHERE c.id = ?
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, changelog_id)
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="变更记录不存在")
            return _decorate(row_to_dict(cursor, row))
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/changelog/by-spc/{spc_message_id}")
def get_changelog_for_spc(spc_message_id: int, user: dict = Depends(require_user)):
    """All 工艺参数 changes associated with a given SPC (cycle) message,
    supporting the Machine -> SPC -> 工艺参数 Changelog hierarchy."""
    del user
    sql = f"""
        SELECT
            {CHANGELOG_SELECT}
        {CHANGELOG_FROM}
        WHERE c.spc_message_id = ?
        ORDER BY c.detected_at
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, spc_message_id)
            return [_decorate(row_to_dict(cursor, row)) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error