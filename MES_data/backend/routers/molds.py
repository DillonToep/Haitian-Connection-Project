from contextlib import closing
from datetime import date, timedelta
import json
import shutil
import uuid

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from ..config import MOLD_UPLOAD_DIR
from ..database import get_connection, row_to_dict
from ..security import require_editor, require_user
from ..parameter_labels import PARAMETER_LABELS, EXCLUDED_FROM_TARGETS, categorize_tag
from ..schemas import (
    MachineTypeAssignmentRequest,
    MachineTypeCreateRequest,
    MachineTypeRenameRequest,
    MoldAssignmentRequest,
    MoldParametersUpdateRequest,
    MoldUpdateRequest,
    MoldExtendedInfoRequest
)



router = APIRouter(prefix="/api", tags=["molds"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

def _check_machine_type_match(cursor, device_id: str, sheet_machine_type: str | None, force: bool) -> None:
    """Compares a mold specification sheet's machine type name (机型)
    against the physical device's own 机型 (dbo.device_profiles.machine_type,
    set from the dashboard card). If both are set and don't match, this
    is presumably the wrong sheet for this machine -- raise a 409 with
    both names so the frontend can warn the user and offer a forced
    override (force=True). If either side has no name set, there's
    nothing to compare against, so it's always allowed."""
    if force:
        return
    row = cursor.execute(
        "SELECT machine_type FROM dbo.device_profiles WHERE device_id = ?", device_id
    ).fetchone()
    device_machine_type = row.machine_type if row else None
    if not device_machine_type or not sheet_machine_type:
        return
    if device_machine_type.strip().casefold() != sheet_machine_type.strip().casefold():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "machine_type_mismatch",
                "device_machine_type": device_machine_type,
                "sheet_machine_type": sheet_machine_type,
                "message": f"设备机型「{device_machine_type}」与规格表机型「{sheet_machine_type}」不一致，是否仍要应用？",
            },
        )


def _cavity_rows_for(cavities: int) -> list[str]:
    """['1', '2', ..., str(cavities)] -- one temperature entry per item."""
    return [str(i) for i in range(1, cavities + 1)]


def _parse_cavity_values(raw: str | None, expected_labels: list[str]) -> dict[str, dict[str, float | None]]:
    """raw is a JSON string like
    {"1": {"temperature_c": 25.5, "tolerance_pct": 5}, "2": {...}}.
    Unknown/missing labels default to NULL; anything not in
    expected_labels is ignored (defends against a stale/mismatched
    cavity count in the form)."""
    parsed = {}
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="cavity_temperatures 格式不正确") from None

    def _as_float(value, label):
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"数值无效：{label}") from None

    result = {}
    for label in expected_labels:
        entry = parsed.get(label)
        if entry is None:
            entry = {}
        elif not isinstance(entry, dict):
            # Back-compat: old shape was label -> temperature number only.
            entry = {"temperature_c": entry}
        result[label] = {
            "temperature_c": _as_float(entry.get("temperature_c"), label),
            "tolerance_pct": _as_float(entry.get("tolerance_pct"), label),
        }
    return result


def _parse_cleaning_fields(
    requires_cleaning_raw: str,
    interval_raw: str | None,
    duration_raw: str | None,
) -> tuple[bool, float | None, int | None]:
    """Interpret the 需要清洗 checkbox + its two follow-up fields from a
    multipart form submission (all arrive as strings). When the checkbox
    is off, the interval/duration are discarded (forced to NULL) even if
    stray values were left in the inputs. When it's on, both values are
    required and must be positive."""
    requires_cleaning = requires_cleaning_raw == "1"
    if not requires_cleaning:
        return False, None, None

    try:
        interval = float(interval_raw) if interval_raw not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="清洗检查间隔格式不正确") from None

    try:
        duration = int(duration_raw) if duration_raw not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="预计清洗时长格式不正确") from None

    if interval is None or interval <= 0:
        raise HTTPException(status_code=400, detail="请填写有效的清洗检查间隔（小时）")
    if duration is None or duration <= 0:
        raise HTTPException(status_code=400, detail="请填写有效的预计清洗时长（分钟）")

    return True, interval, duration


def _parse_max_output(raw: str | None) -> int | None:
    """max_output arrives as a plain (optional) string from multipart
    forms -- blank means "no limit", same convention as the cleaning
    interval/duration fields above."""
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="最大产量格式不正确") from None
    if value <= 0:
        raise HTTPException(status_code=400, detail="最大产量必须大于 0")
    return value


def _attach_images_and_temps(cursor, records: list[dict]) -> list[dict]:
    if not records:
        return records
    ids = [r["id"] for r in records]
    placeholders = ",".join("?" for _ in ids)

    cursor.execute(
        f"""
        SELECT mold_id, id, file_path, is_face, sort_order
        FROM dbo.mold_images
        WHERE mold_id IN ({placeholders})
        ORDER BY mold_id, sort_order
        """,
        ids,
    )
    images_by_mold: dict[int, list[dict]] = {}
    for row in cursor.fetchall():
        images_by_mold.setdefault(row.mold_id, []).append(
            {"id": row.id, "url": row.file_path, "is_face": bool(row.is_face)}
        )

    cursor.execute(
        f"""
        SELECT mold_id, cavity_label, temperature_c, tolerance_pct
        FROM dbo.mold_cavity_temperatures
        WHERE mold_id IN ({placeholders})
        ORDER BY mold_id, sort_order
        """,
        ids,
    )
    temps_by_mold: dict[int, list[dict]] = {}
    for row in cursor.fetchall():
        temps_by_mold.setdefault(row.mold_id, []).append(
            {
                "cavity_label": row.cavity_label,
                "temperature_c": row.temperature_c,
                "tolerance_pct": row.tolerance_pct,
            }
        )

    for record in records:
        images = images_by_mold.get(record["id"], [])
        record["images"] = images
        face = next((img for img in images if img["is_face"]), None)
        record["face_image_url"] = face["url"] if face else (images[0]["url"] if images else None)
        record["cavity_temperatures"] = temps_by_mold.get(record["id"], [])

    return records


@router.get("/molds")
def get_molds(user: dict = Depends(require_user)):
    del user
    sql = """
        SELECT
            m.id, m.mold_code, m.mold_name, m.product_code,
            m.cavities, m.remark, m.is_active,
            m.requires_cleaning, m.cleaning_interval_hours, m.cleaning_duration_minutes,
            m.max_output, m.total_output,
            a.device_id AS mounted_device_id, a.mounted_at
        FROM dbo.molds AS m
        LEFT JOIN dbo.device_mold_assignments AS a
            ON a.mold_id = m.id AND a.unmounted_at IS NULL
        ORDER BY m.is_active DESC, m.mold_code
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            records = [row_to_dict(cursor, row) for row in cursor.fetchall()]
            return _attach_images_and_temps(cursor, records)
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error



@router.get("/molds/parameter-defaults")
def get_mold_parameter_defaults(user: dict = Depends(require_user)):
    """The global 高级工艺参数 template used to seed every *new* mold going
    forward (see create_mold below). Registered before
    /molds/{mold_id}/parameters so the literal 'parameter-defaults' path
    segment isn't swallowed by that route's int-typed mold_id."""
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat "
                "FROM dbo.mold_parameter_defaults"
            )
            saved = {row.parameter_id: row for row in cursor.fetchall()}
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    parameters = []
    for tag, meta in PARAMETER_LABELS.items():
        if not meta["use"] or tag in EXCLUDED_FROM_TARGETS:
            continue
        row = saved.get(tag)
        parameters.append(
            {
                "parameter_id": tag,
                "label": meta["label"],
                "category": categorize_tag(tag, meta["label"]),
                "value": row.target_value if row else None,
                "tolerance_mode": row.tolerance_mode if row else "percent",
                "tolerance_percent": float(row.tolerance_percent) if row and row.tolerance_percent is not None else None,
                "tolerance_flat": float(row.tolerance_flat) if row and row.tolerance_flat is not None else None,
            }
        )
    return {"parameters": parameters}


@router.put("/molds/parameter-defaults")
def update_mold_parameter_defaults(
    data: MoldParametersUpdateRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    valid_tags = set(PARAMETER_LABELS.keys()) - EXCLUDED_FROM_TARGETS
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM dbo.mold_parameter_defaults")
            for item in data.parameters:
                if item.parameter_id not in valid_tags:
                    continue
                value = item.value.strip() if item.value else None
                tol_percent = item.tolerance_percent if item.tolerance_mode == "percent" else None
                tol_flat = item.tolerance_flat if item.tolerance_mode == "flat" else None
                if not value and tol_percent is None and tol_flat is None:
                    continue  # blank row, nothing worth saving as a default
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_parameter_defaults
                        (parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat, updated_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    item.parameter_id,
                    value,
                    item.tolerance_mode,
                    tol_percent,
                    tol_flat,
                    user["id"],
                )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


def _get_machine_type_or_404(cursor, mold_id: int, machine_type_id: int):
    row = cursor.execute(
        "SELECT id, mold_id, machine_type, is_main FROM dbo.mold_machine_types WHERE id = ? AND mold_id = ?",
        machine_type_id, mold_id,
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="机型不存在")
    return row


def _seed_machine_type_from_defaults(cursor, machine_type_id: int):
    """Seed a brand-new machine type's 高级工艺参数 from the global
    defaults template (模具管理 -> 默认参数设置) -- same behavior create_mold
    used to apply directly to a mold, now applied per machine type."""
    cursor.execute(
        "SELECT parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat "
        "FROM dbo.mold_parameter_defaults"
    )
    for default_row in cursor.fetchall():
        cursor.execute(
            """
            INSERT INTO dbo.mold_parameter_targets
                (mold_id, machine_type_id, parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat)
            VALUES (NULL, ?, ?, ?, ?, ?, ?)
            """,
            machine_type_id,
            default_row.parameter_id,
            default_row.target_value,
            default_row.tolerance_mode,
            default_row.tolerance_percent,
            default_row.tolerance_flat,
        )


@router.get("/molds/{mold_id}/machine-types")
def get_mold_machine_types(mold_id: int, user: dict = Depends(require_user)):
    """The 机型 list for a mold -- Mold -> Machine Type -> Specifications.
    Each entry is its own independent specification record; is_main marks
    the one machine type mqtt_monitor.py checks tolerances against."""
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在")
            cursor.execute(
                """
                SELECT id, machine_type, is_main, created_at
                FROM dbo.mold_machine_types
                WHERE mold_id = ?
                ORDER BY is_main DESC, created_at
                """,
                mold_id,
            )
            return {
                "mold_id": mold_id,
                "machine_types": [row_to_dict(cursor, row) for row in cursor.fetchall()],
            }
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/molds/{mold_id}/machine-types", status_code=201)
def create_mold_machine_type(
    mold_id: int,
    data: MachineTypeCreateRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            existing_count = cursor.execute(
                "SELECT COUNT(*) FROM dbo.mold_machine_types WHERE mold_id = ?", mold_id
            ).fetchone()[0]
            is_main = 0 if existing_count else 1

            name = (data.machine_type or "").strip() or f"新机型{existing_count + 1}"

            machine_type_id = cursor.execute(
                """
                INSERT INTO dbo.mold_machine_types (mold_id, machine_type, is_main, created_by)
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?)
                """,
                mold_id, name, is_main, user["id"],
            ).fetchone()[0]

            _seed_machine_type_from_defaults(cursor, machine_type_id)

            connection.commit()
            return {"status": "ok", "id": machine_type_id, "is_main": bool(is_main)}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.put("/molds/{mold_id}/machine-types/{machine_type_id}")
def rename_mold_machine_type(
    mold_id: int,
    machine_type_id: int,
    data: MachineTypeRenameRequest,
    user: dict = Depends(require_user),
):
    """Renames a machine type in place -- its specifications, is_main
    flag, and any devices currently pointed at it (see
    dbo.device_mold_assignments.machine_type_id) are untouched; only the
    display name changes. This is how the auto-created "默认机型" a brand
    new mold starts with (see create_mold) gets renamed to something
    meaningful."""
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            _get_machine_type_or_404(cursor, mold_id, machine_type_id)
            cursor.execute(
                "UPDATE dbo.mold_machine_types SET machine_type = ? WHERE id = ?",
                data.machine_type.strip(),
                machine_type_id,
            )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/molds/{mold_id}/machine-types/{machine_type_id}/set-main")
def set_main_machine_type(mold_id: int, machine_type_id: int, user: dict = Depends(require_user)):
    """Marks this machine type as the mold's main one -- this only
    controls which machine type seeds a *new* mold's/machine type's
    default specs and which one is labeled "主要机型" in 模具管理. It no
    longer determines which specifications any device's notifications
    use -- that's driven per-device by dbo.device_mold_assignments.
    machine_type_id (see _fetch_mold_targets in mqtt_monitor.py)."""
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            _get_machine_type_or_404(cursor, mold_id, machine_type_id)
            cursor.execute(
                "UPDATE dbo.mold_machine_types SET is_main = 0 WHERE mold_id = ? AND is_main = 1",
                mold_id,
            )
            cursor.execute(
                "UPDATE dbo.mold_machine_types SET is_main = 1 WHERE id = ?",
                machine_type_id,
            )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.delete("/molds/{mold_id}/machine-types/{machine_type_id}")
def delete_mold_machine_type(mold_id: int, machine_type_id: int, user: dict = Depends(require_user)):
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            row = _get_machine_type_or_404(cursor, mold_id, machine_type_id)

            remaining = cursor.execute(
                "SELECT COUNT(*) FROM dbo.mold_machine_types WHERE mold_id = ?", mold_id
            ).fetchone()[0]
            if remaining <= 1:
                raise HTTPException(status_code=400, detail="模具至少需要保留一个机型")

            in_use = cursor.execute(
                """
                SELECT TOP 1 device_id FROM dbo.device_mold_assignments
                WHERE machine_type_id = ? AND unmounted_at IS NULL
                """,
                machine_type_id,
            ).fetchone()
            if in_use:
                raise HTTPException(
                    status_code=400,
                    detail=f"设备 {in_use.device_id} 正在使用该机型，请先为该设备切换机型后再删除",
                )

            # FK ON DELETE CASCADE handles mold_parameter_targets /
            # mold_extended_info rows tied to this machine type.
            cursor.execute("DELETE FROM dbo.mold_machine_types WHERE id = ?", machine_type_id)

            if row.is_main:
                cursor.execute(
                    """
                    UPDATE dbo.mold_machine_types SET is_main = 1
                    WHERE id = (
                        SELECT TOP 1 id FROM dbo.mold_machine_types
                        WHERE mold_id = ? ORDER BY created_at
                    )
                    """,
                    mold_id,
                )

            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@router.get("/molds/{mold_id}/machine-types/{machine_type_id}/parameters")
def get_mold_machine_type_parameters(
    mold_id: int,
    machine_type_id: int,
    user: dict = Depends(require_user),
):
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            _get_machine_type_or_404(cursor, mold_id, machine_type_id)
            cursor.execute(
                "SELECT parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat "
                "FROM dbo.mold_parameter_targets WHERE machine_type_id = ?",
                machine_type_id,
            )
            saved = {row.parameter_id: row for row in cursor.fetchall()}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    parameters = []
    for tag, meta in PARAMETER_LABELS.items():
        if not meta["use"] or tag in EXCLUDED_FROM_TARGETS:
            continue
        row = saved.get(tag)
        parameters.append(
            {
                "parameter_id": tag,
                "label": meta["label"],
                "category": categorize_tag(tag, meta["label"]),
                "value": row.target_value if row else None,
                "tolerance_mode": row.tolerance_mode if row else "percent",
                "tolerance_percent": float(row.tolerance_percent) if row and row.tolerance_percent is not None else None,
                "tolerance_flat": float(row.tolerance_flat) if row and row.tolerance_flat is not None else None,
            }
        )
    return {"parameters": parameters}


@router.put("/molds/{mold_id}/machine-types/{machine_type_id}/parameters")
def update_mold_machine_type_parameters(
    mold_id: int,
    machine_type_id: int,
    data: MoldParametersUpdateRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    valid_tags = set(PARAMETER_LABELS.keys()) - EXCLUDED_FROM_TARGETS
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            _get_machine_type_or_404(cursor, mold_id, machine_type_id)

            cursor.execute(
                "DELETE FROM dbo.mold_parameter_targets WHERE machine_type_id = ?",
                machine_type_id,
            )
            for item in data.parameters:
                if item.parameter_id not in valid_tags:
                    continue
                value = item.value.strip() if item.value else None
                tol_percent = item.tolerance_percent if item.tolerance_mode == "percent" else None
                tol_flat = item.tolerance_flat if item.tolerance_mode == "flat" else None
                if not value and tol_percent is None and tol_flat is None:
                    continue
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_parameter_targets
                        (mold_id, machine_type_id, parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat)
                    VALUES (NULL, ?, ?, ?, ?, ?, ?)
                    """,
                    machine_type_id,
                    item.parameter_id,
                    value,
                    item.tolerance_mode,
                    tol_percent,
                    tol_flat,
                )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error




@router.get("/molds/{mold_id}/machine-types/{machine_type_id}/extended")
def get_mold_extended_info(mold_id: int, machine_type_id: int, user: dict = Depends(require_user)):
    """The free-form 注塑成型条件参数表 fields (header/material/weight/
    hot-runner/water-mold-temp/injection-method/residual-position/cycle
    totals/operation setup) that don't have dedicated columns -- see
    setup_mold_extended_info.sql / setup_mold_machine_types.sql. Scoped to
    one Mold + Machine Type combination; returns {} if nothing has been
    saved for it yet."""
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            _get_machine_type_or_404(cursor, mold_id, machine_type_id)
            row = cursor.execute(
                "SELECT info_json FROM dbo.mold_extended_info WHERE machine_type_id = ?", machine_type_id
            ).fetchone()
            fields = json.loads(row.info_json) if row and row.info_json else {}
            return {"mold_id": mold_id, "machine_type_id": machine_type_id, "fields": fields}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.put("/molds/{mold_id}/machine-types/{machine_type_id}/extended")
def update_mold_extended_info(
    mold_id: int,
    machine_type_id: int,
    data: MoldExtendedInfoRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    payload = json.dumps(data.fields, ensure_ascii=False)
    sql = """
        MERGE dbo.mold_extended_info AS target
        USING (SELECT ? AS machine_type_id) AS src
        ON target.machine_type_id = src.machine_type_id
        WHEN MATCHED THEN
            UPDATE SET info_json = ?, updated_at = SYSUTCDATETIME(), updated_by = ?
        WHEN NOT MATCHED THEN
            INSERT (mold_id, machine_type_id, info_json, updated_by)
            VALUES (NULL, src.machine_type_id, ?, ?);
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            _get_machine_type_or_404(cursor, mold_id, machine_type_id)
            cursor.execute(sql, machine_type_id, payload, user["id"], payload, user["id"])

            machine_model = data.fields.get("machine_model")
            if isinstance(machine_model, str) and machine_model.strip():
                cursor.execute(
                    "UPDATE dbo.mold_machine_types SET machine_type = ? WHERE id = ?",
                    machine_model.strip(), machine_type_id,
                )

            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@router.get("/molds/{mold_id}/output")
def get_mold_output(
    mold_id: int,
    granularity: str = Query("day", pattern="^(day|week)$"),
    periods: int = Query(30, ge=1, le=366),
    user: dict = Depends(require_user),
):
    del user
    date_expr = "CAST(produced_at AS DATE)" if granularity == "day" else \
                "DATEADD(day, -DATEPART(weekday, produced_at) + 1, CAST(produced_at AS DATE))"
    sql_buckets = f"""
        SELECT {date_expr} AS bucket, COUNT(*) AS count
        FROM dbo.mold_production_log
        WHERE mold_id = ?
        GROUP BY {date_expr}
        ORDER BY bucket DESC
        OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
    """
    # Independent of the requested granularity/periods -- these two
    # convenience totals always mean "today" and "this calendar week"
    # (Mon-Sun), same window the dashboard's 模次/产量 figures use.
    sql_today = """
        SELECT COUNT(*) AS count
        FROM dbo.mold_production_log
        WHERE mold_id = ? AND CAST(produced_at AS DATE) = CAST(SYSDATETIME() AS DATE)
    """
    sql_week = """
        SELECT COUNT(*) AS count
        FROM dbo.mold_production_log
        WHERE mold_id = ?
          AND produced_at >= DATEADD(
                day, -DATEPART(weekday, CAST(SYSDATETIME() AS DATE)) + 1,
                CAST(SYSDATETIME() AS DATE)
              )
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute(
                "SELECT total_output, max_output FROM dbo.molds WHERE id = ?", mold_id
            ).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            cursor.execute(sql_buckets, mold_id, periods)
            buckets = [{"date": r.bucket.isoformat(), "count": r.count} for r in cursor.fetchall()]

            today_output = cursor.execute(sql_today, mold_id).fetchone().count
            week_output = cursor.execute(sql_week, mold_id).fetchone().count

            return {
                "mold_id": mold_id,
                "total_output": mold.total_output,
                "max_output": mold.max_output,
                "today_output": today_output,
                "week_output": week_output,
                "buckets": list(reversed(buckets)),
            }
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/molds/{mold_id}/output/reset")
def reset_mold_output(mold_id: int, user: dict = Depends(require_user)):
    """Zero out this mold's own production counters (今日/本周/累计产量,
    plus its max_output alert baseline) -- reachable directly from
    模具管理, independent of whether the mold is currently mounted on a
    device. If it IS currently mounted, this also resets that device's
    模次 display baseline (dbo.device_cycle_resets) the same way the
    device-detail page's reset button does, so the two views never drift
    apart from each other."""
    require_editor(user)
    sql_current_device = """
        SELECT device_id FROM dbo.device_mold_assignments
        WHERE mold_id = ? AND unmounted_at IS NULL
    """
    sql_latest_cycle = """
        SELECT TOP 1 cycle_number
        FROM dbo.vw_machine_spc
        WHERE device_id = ?
        ORDER BY data_time DESC, raw_message_id DESC
    """
    sql_upsert_cycle = """
        MERGE dbo.device_cycle_resets AS target
        USING (SELECT ? AS device_id) AS src
        ON target.device_id = src.device_id
        WHEN MATCHED THEN
            UPDATE SET reset_cycle_number = ?, reset_at = SYSUTCDATETIME(), reset_by = ?
        WHEN NOT MATCHED THEN
            INSERT (device_id, reset_cycle_number, reset_by)
            VALUES (src.device_id, ?, ?);
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            row = cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            cursor.execute("DELETE FROM dbo.mold_production_log WHERE mold_id = ?", mold_id)
            cursor.execute("UPDATE dbo.molds SET total_output = 0 WHERE id = ?", mold_id)
            cursor.execute(
                "DELETE FROM dbo.mold_output_alerts WHERE mold_id = ? AND acknowledged_at IS NULL",
                mold_id,
            )

            device_row = cursor.execute(sql_current_device, mold_id).fetchone()
            if device_row is not None:
                device_id = device_row.device_id
                cycle_row = cursor.execute(sql_latest_cycle, device_id).fetchone()
                baseline = cycle_row.cycle_number if cycle_row and cycle_row.cycle_number is not None else 0
                cursor.execute(sql_upsert_cycle, device_id, baseline, user["id"], baseline, user["id"])

            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@router.put("/molds/{mold_id}/parameters")
def update_mold_parameters(
    mold_id: int,
    data: MoldParametersUpdateRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    valid_tags = set(PARAMETER_LABELS.keys()) - EXCLUDED_FROM_TARGETS
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            cursor.execute("DELETE FROM dbo.mold_parameter_targets WHERE mold_id = ?", mold_id)
            for item in data.parameters:
                if item.parameter_id not in valid_tags:
                    continue
                value = item.value.strip() if item.value else None
                tol_percent = item.tolerance_percent if item.tolerance_mode == "percent" else None
                tol_flat = item.tolerance_flat if item.tolerance_mode == "flat" else None
                if not value and tol_percent is None and tol_flat is None:
                    continue  # blank row, nothing to save
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_parameter_targets
                        (mold_id, parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    mold_id,
                    item.parameter_id,
                    value,
                    item.tolerance_mode,
                    tol_percent,
                    tol_flat,
                )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error



@router.post("/molds", status_code=201)
async def create_mold(
    user: dict = Depends(require_user),
    mold_code: str = Form(..., max_length=100),
    mold_name: str = Form(..., max_length=200),
    cavities: int = Form(..., ge=1, le=10_000),
    remark: str | None = Form(None, max_length=500),
    cavity_temperatures: str | None = Form(None),
    face_index: int = Form(0),
    requires_cleaning: str = Form("0"),
    cleaning_interval_hours: str | None = Form(None),
    cleaning_duration_minutes: str | None = Form(None),
    max_output: str | None = Form(None),
    images: list[UploadFile] = File(default=[]),
):
    require_editor(user)

    if len(images) < 1:
        raise HTTPException(status_code=400, detail="至少需要上传一张项目图片")
    for image in images:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的图片类型：{image.content_type}")
    if not (0 <= face_index < len(images)):
        raise HTTPException(status_code=400, detail="封面图片选择无效")

    expected_labels = _cavity_rows_for(cavities)
    temps = _parse_cavity_values(cavity_temperatures, expected_labels)
    cleaning_flag, cleaning_interval, cleaning_duration = _parse_cleaning_fields(
        requires_cleaning, cleaning_interval_hours, cleaning_duration_minutes
    )
    max_output_value = _parse_max_output(max_output)

    sql_insert_mold = """
        INSERT INTO dbo.molds
            (mold_code, mold_name, cavities, remark, created_by,
             requires_cleaning, cleaning_interval_hours, cleaning_duration_minutes,
             max_output)
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold_id = cursor.execute(
                sql_insert_mold,
                mold_code.strip(),
                mold_name.strip(),
                cavities,
                remark.strip() if remark else None,
                user["id"],
                cleaning_flag,
                cleaning_interval,
                cleaning_duration,
                max_output_value,
            ).fetchone()[0]

            for sort_order, label in enumerate(expected_labels):
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_cavity_temperatures
                        (mold_id, cavity_label, temperature_c, tolerance_pct, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    mold_id,
                    label,
                    temps[label]["temperature_c"],
                    temps[label]["tolerance_pct"],
                    sort_order,
                )

            # ---- every mold needs at least one 机型 to hold its
            # specifications against (Mold -> Machine Type ->
            # Specifications). A brand-new mold gets one default machine
            # type, auto-flagged as main, seeded from the global defaults
            # template (模具管理 -> 默认参数设置) the same way a mold's specs
            # used to be seeded directly. The user can rename/replace it
            # or add more machine types afterwards. ----
            default_machine_type_id = cursor.execute(
                """
                INSERT INTO dbo.mold_machine_types (mold_id, machine_type, is_main, created_by)
                OUTPUT INSERTED.id
                VALUES (?, ?, 1, ?)
                """,
                mold_id, "默认机型", user["id"],
            ).fetchone()[0]
            _seed_machine_type_from_defaults(cursor, default_machine_type_id)

            # ---- image files (runs once, not once-per-cavity) ----
            mold_dir = MOLD_UPLOAD_DIR / str(mold_id)
            mold_dir.mkdir(parents=True, exist_ok=True)
            for image_index, image in enumerate(images):
                extension = (image.filename or "").rsplit(".", 1)[-1].lower() if "." in (image.filename or "") else "jpg"
                safe_name = f"{uuid.uuid4().hex}.{extension}"
                dest = mold_dir / safe_name
                content = await image.read()
                dest.write_bytes(content)
                web_path = f"/static/uploads/molds/{mold_id}/{safe_name}"
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_images
                        (mold_id, file_path, is_face, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    mold_id,
                    web_path,
                    1 if image_index == face_index else 0,
                    image_index,
                )

            connection.commit()
            return {"status": "ok", "id": mold_id}
    except pyodbc.IntegrityError as error:
        raise HTTPException(status_code=409, detail="项目编号已经存在") from error
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.put("/molds/{mold_id}")
async def update_mold(
    mold_id: int,
    user: dict = Depends(require_user),
    mold_code: str = Form(..., max_length=100),
    mold_name: str = Form(..., max_length=200),
    cavities: int = Form(..., ge=1, le=10_000),
    remark: str | None = Form(None, max_length=500),
    is_active: str = Form("1"),
    cavity_temperatures: str | None = Form(None),
    requires_cleaning: str = Form("0"),
    cleaning_interval_hours: str | None = Form(None),
    cleaning_duration_minutes: str | None = Form(None),
    max_output: str | None = Form(None),
    keep_image_ids: str | None = Form(None),   # JSON array of existing image ids to keep
    face_image_id: int | None = Form(None),    # id of a kept existing image to use as cover
    face_new_index: int | None = Form(None),   # index within the new `images` list to use as cover
    images: list[UploadFile] = File(default=[]),
):
    require_editor(user)

    for image in images:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的图片类型：{image.content_type}")

    cleaning_flag, cleaning_interval, cleaning_duration = _parse_cleaning_fields(
        requires_cleaning, cleaning_interval_hours, cleaning_duration_minutes
    )
    max_output_value = _parse_max_output(max_output)

    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id)
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            cursor.execute(
                "SELECT id, file_path, is_face FROM dbo.mold_images WHERE mold_id = ? ORDER BY sort_order",
                mold_id,
            )
            existing_images = [
                {"id": row.id, "file_path": row.file_path, "is_face": bool(row.is_face)}
                for row in cursor.fetchall()
            ]

            if keep_image_ids is not None:
                try:
                    keep_ids = set(json.loads(keep_image_ids))
                except json.JSONDecodeError:
                    raise HTTPException(status_code=400, detail="keep_image_ids 格式不正确") from None
            else:
                # Not provided -- text-only edit that doesn't touch images at all.
                keep_ids = {img["id"] for img in existing_images}

            kept_images = [img for img in existing_images if img["id"] in keep_ids]
            removed_images = [img for img in existing_images if img["id"] not in keep_ids]

            total_images = len(kept_images) + len(images)
            if total_images < 1:
                raise HTTPException(status_code=400, detail="至少需要保留一张项目图片")

            expected_labels = _cavity_rows_for(cavities)
            temps = _parse_cavity_values(cavity_temperatures, expected_labels)

            # ---- text fields ----
            cursor.execute(
                """
                UPDATE dbo.molds
                SET mold_code = ?, mold_name = ?, cavities = ?, remark = ?,
                    is_active = ?, requires_cleaning = ?, cleaning_interval_hours = ?,
                    cleaning_duration_minutes = ?, max_output = ?, updated_at = SYSDATETIME()
                WHERE id = ?
                """,
                mold_code.strip(),
                mold_name.strip(),
                cavities,
                remark.strip() if remark else None,
                1 if is_active == "1" else 0,
                cleaning_flag,
                cleaning_interval,
                cleaning_duration,
                max_output_value,
                mold_id,
            )

            # ---- cavity temperatures: replace wholesale, same as create ----
            cursor.execute("DELETE FROM dbo.mold_cavity_temperatures WHERE mold_id = ?", mold_id)
            for sort_order, label in enumerate(expected_labels):
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_cavity_temperatures
                        (mold_id, cavity_label, temperature_c, tolerance_pct, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    mold_id,
                    label,
                    temps[label]["temperature_c"],
                    temps[label]["tolerance_pct"],
                    sort_order,
                )

            # ---- removed images: delete rows + files on disk ----
            for img in removed_images:
                cursor.execute("DELETE FROM dbo.mold_images WHERE id = ?", img["id"])
                filename = img["file_path"].rsplit("/", 1)[-1]
                disk_path = MOLD_UPLOAD_DIR / str(mold_id) / filename
                try:
                    disk_path.unlink(missing_ok=True)
                except OSError:
                    pass

            # ---- kept images: reassign sort order + cover flag ----
            for sort_order, img in enumerate(kept_images):
                is_face = 1 if (face_image_id is not None and img["id"] == face_image_id) else 0
                cursor.execute(
                    "UPDATE dbo.mold_images SET is_face = ?, sort_order = ? WHERE id = ?",
                    is_face,
                    sort_order,
                    img["id"],
                )

            # ---- newly uploaded images ----
            mold_dir = MOLD_UPLOAD_DIR / str(mold_id)
            mold_dir.mkdir(parents=True, exist_ok=True)
            for new_index, image in enumerate(images):
                extension = (image.filename or "").rsplit(".", 1)[-1].lower() if "." in (image.filename or "") else "jpg"
                safe_name = f"{uuid.uuid4().hex}.{extension}"
                dest = mold_dir / safe_name
                content = await image.read()
                dest.write_bytes(content)
                web_path = f"/static/uploads/molds/{mold_id}/{safe_name}"
                is_face = 1 if (face_new_index is not None and new_index == face_new_index) else 0
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_images
                        (mold_id, file_path, is_face, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    mold_id,
                    web_path,
                    is_face,
                    len(kept_images) + new_index,
                )

            # ---- safety net: guarantee exactly one cover image ----
            cursor.execute(
                "SELECT COUNT(*) FROM dbo.mold_images WHERE mold_id = ? AND is_face = 1",
                mold_id,
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    """
                    UPDATE dbo.mold_images SET is_face = 1
                    WHERE id = (
                        SELECT TOP 1 id FROM dbo.mold_images
                        WHERE mold_id = ? ORDER BY sort_order
                    )
                    """,
                    mold_id,
                )

            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.IntegrityError as error:
        raise HTTPException(status_code=409, detail="项目编号已经存在") from error
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@router.delete("/molds/{mold_id}")
def delete_mold(mold_id: int, user: dict = Depends(require_user)):
    """Permanently remove a mold record -- including its mount history,
    saved 高级工艺参数 targets, and image files on disk. Blocked while the
    mold is currently mounted on a device; unmount it first (DELETE
    /api/devices/{device_id}/mold) so an active assignment is never
    silently deleted out from under a running device."""
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            row = cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            mounted = cursor.execute(
                "SELECT 1 FROM dbo.device_mold_assignments WHERE mold_id = ? AND unmounted_at IS NULL",
                mold_id,
            ).fetchone()
            if mounted:
                raise HTTPException(status_code=400, detail="该模具当前已装机，请先卸载后再删除")
            cursor.execute("DELETE FROM dbo.device_mold_assignments WHERE mold_id = ?", mold_id)
            # Cascades to mold_parameter_targets / mold_extended_info rows
            # for every machine type this mold has (see
            # setup_mold_machine_types.sql ON DELETE CASCADE).
            cursor.execute("DELETE FROM dbo.mold_machine_types WHERE mold_id = ?", mold_id)
            cursor.execute("DELETE FROM dbo.mold_output_alerts WHERE mold_id = ?", mold_id)
            cursor.execute("DELETE FROM dbo.mold_production_log WHERE mold_id = ?", mold_id)
            cursor.execute("DELETE FROM dbo.molds WHERE id = ?", mold_id)
            connection.commit()

            shutil.rmtree(MOLD_UPLOAD_DIR / str(mold_id), ignore_errors=True)
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error




@router.get("/devices/{device_id}/mold")
def get_current_mold(device_id: str, user: dict = Depends(require_user)):
    """The device's currently active mold assignment, or null if none."""
    del user
    sql = """
        SELECT TOP 1
            a.id AS assignment_id, a.mounted_at, a.remark,
            a.machine_type_id, mt.machine_type AS machine_type_name,
            m.id AS mold_id, m.mold_code, m.mold_name,
            m.product_code, m.cavities,
            m.requires_cleaning, m.cleaning_interval_hours, m.cleaning_duration_minutes
        FROM dbo.device_mold_assignments AS a
        INNER JOIN dbo.molds AS m ON m.id = a.mold_id
        LEFT JOIN dbo.mold_machine_types AS mt ON mt.id = a.machine_type_id
        WHERE a.device_id = ? AND a.unmounted_at IS NULL
        ORDER BY a.mounted_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            row = cursor.fetchone()
            return row_to_dict(cursor, row) if row else None
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/devices/{device_id}/mold")
def assign_mold(
    device_id: str,
    data: MoldAssignmentRequest,
    user: dict = Depends(require_user),
):
    """Assign (mount) a mold + Machine Type onto a device. Since
    dbo.device_mold_assignments only allows one active row per device AND
    one active row per mold (see UX_device_mold_active_device /
    UX_device_mold_active_mold in setup_web_database.sql), this both:
      1) unmounts whatever is currently on this device, and
      2) unmounts this mold from wherever else it's currently active --
         effectively "transferring" it here, rather than erroring, since
         moving a mold between machines is a normal shop-floor operation.

    machine_type_id must belong to the mold being assigned -- this is
    what tolerance/production notifications for this device will resolve
    specifications through from now on (Physical Machine -> Mold ->
    Machine Type -> Specifications; see _fetch_mold_targets in
    mqtt_monitor.py). No specification values are copied anywhere -- only
    this pointer is stored.
    """
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute(
                "SELECT id, is_active FROM dbo.molds WHERE id = ?", data.mold_id
            ).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在")
            if not mold.is_active:
                raise HTTPException(status_code=400, detail="该模具已停用，无法分配")

            machine_type = cursor.execute(
                "SELECT id, machine_type FROM dbo.mold_machine_types WHERE id = ? AND mold_id = ?",
                data.machine_type_id, data.mold_id,
            ).fetchone()
            if machine_type is None:
                raise HTTPException(status_code=400, detail="所选机型不属于该模具")

            _check_machine_type_match(cursor, device_id, machine_type.machine_type, data.force)

            cursor.execute(
                """
                UPDATE dbo.device_mold_assignments
                SET unmounted_at = SYSDATETIME()
                WHERE device_id = ? AND unmounted_at IS NULL
                """,
                device_id,
            )
            cursor.execute(
                """
                UPDATE dbo.device_mold_assignments
                SET unmounted_at = SYSDATETIME()
                WHERE mold_id = ? AND unmounted_at IS NULL
                """,
                data.mold_id,
            )
            cursor.execute(
                """
                INSERT INTO dbo.device_mold_assignments
                    (device_id, mold_id, machine_type_id, operator_user_id, remark)
                VALUES (?, ?, ?, ?, ?)
                """,
                device_id,
                data.mold_id,
                data.machine_type_id,
                user["id"],
                data.remark.strip() if data.remark else None,
            )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.put("/devices/{device_id}/machine-type")
def update_device_machine_type(
    device_id: str,
    data: MachineTypeAssignmentRequest,
    user: dict = Depends(require_user),
):
    """Switch which Machine Type's specifications the device's *currently
    mounted* mold uses for tolerance/production notifications, without
    unmounting/remounting -- mounted_at, production-log attribution, etc.
    on the active assignment are untouched; only its machine_type_id
    pointer changes. The new machine type must belong to the same mold
    that's already mounted (use POST /api/devices/{device_id}/mold to
    change the mold itself)."""
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            current = cursor.execute(
                "SELECT id, mold_id FROM dbo.device_mold_assignments WHERE device_id = ? AND unmounted_at IS NULL",
                device_id,
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="该设备当前未装模")

            machine_type = cursor.execute(
                "SELECT id, machine_type FROM dbo.mold_machine_types WHERE id = ? AND mold_id = ?",
                data.machine_type_id, data.mold_id,
            ).fetchone()
            if machine_type is None:
                raise HTTPException(status_code=400, detail="所选机型不属于该模具")

            _check_machine_type_match(cursor, device_id, machine_type.machine_type, data.force)

            cursor.execute(
                "UPDATE dbo.device_mold_assignments SET machine_type_id = ? WHERE id = ?",
                data.machine_type_id, current.id,
            )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.delete("/devices/{device_id}/mold")
def unmount_mold(device_id: str, user: dict = Depends(require_user)):
    require_editor(user)
    sql = """
        UPDATE dbo.device_mold_assignments
        SET unmounted_at = SYSDATETIME()
        WHERE device_id = ? AND unmounted_at IS NULL
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="该设备当前未装模")
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/devices/{device_id}/mold-history")
def get_mold_history(device_id: str, user: dict = Depends(require_user)):
    del user
    sql = """
        SELECT
            a.id, a.mold_id, m.mold_code, m.mold_name,
            a.mounted_at, a.unmounted_at, a.remark,
            u.username AS operator_username
        FROM dbo.device_mold_assignments AS a
        INNER JOIN dbo.molds AS m ON m.id = a.mold_id
        LEFT JOIN dbo.app_users AS u ON u.id = a.operator_user_id
        WHERE a.device_id = ?
        ORDER BY a.mounted_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            return [row_to_dict(cursor, row) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error