from contextlib import closing

import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from ..database import get_connection, row_to_dict
from ..parameter_labels import PARAMETER_LABELS, categorize
from ..security import require_editor, require_user


router = APIRouter(prefix="/api", tags=["warnings"])


def _decorate(record: dict) -> dict:
    """Same label/category enrichment as the changelog endpoints, so a
    warning row and its changelog row render identically."""
    meta = PARAMETER_LABELS.get(record["parameter_id"])
    record["label"] = meta["label"] if meta else record["parameter_id"]
    record["category"] = categorize(record["label"])
    return record


@router.get("/warnings")
def get_warnings(user: dict = Depends(require_user)):
    """Pending (unacknowledged) warnings, newest first -- a merge of four
    kinds, each tagged with `warning_type` so the frontend can render/
    route them differently:
      - "parameter": an unacknowledged dbo.tech_parameter_changelog row
        (a 工艺参数 change that broke its mold's tolerance).
      - "output": an unacknowledged dbo.mold_output_alerts row (a mold
        that has produced more cycles than its configured max_output).
      - "auto_assign": an unacknowledged dbo.mold_detection_alerts row
        where mqtt_monitor.py detected a batch parameter-change burst,
        matched it to a mold + machine type above its confidence
        threshold, and auto-assigned it to the device (see
        _handle_parameter_burst / _auto_assign_mold in mqtt_monitor.py).
        Purely informational -- the assignment has already happened by
        the time this warning appears.
      - "unrecognized": an unacknowledged dbo.mold_detection_alerts row
        where a burst was detected but matched no mold above the
        confidence threshold -- the device's assignment was left
        untouched; this just flags that a mold may need to be entered
        into 模具管理.
    """
    del user
    parameter_sql = """
        SELECT TOP 200
            c.id, c.device_id, c.parameter_id, c.previous_value, c.new_value,
            c.data_time, c.detected_at, c.raw_message_id, c.spc_message_id,
            s.cycle_number AS spc_cycle_number
        FROM dbo.tech_parameter_changelog AS c
        LEFT JOIN dbo.vw_machine_spc AS s ON s.raw_message_id = c.spc_message_id
        WHERE c.acknowledged_at IS NULL
        ORDER BY c.detected_at DESC
    """
    output_sql = """
        SELECT TOP 200
            o.id, o.mold_id, o.device_id, o.total_output, o.max_output, o.detected_at,
            m.mold_code, m.mold_name
        FROM dbo.mold_output_alerts AS o
        INNER JOIN dbo.molds AS m ON m.id = o.mold_id
        WHERE o.acknowledged_at IS NULL
        ORDER BY o.detected_at DESC
    """
    detection_sql = """
        SELECT TOP 200
            d.id, d.device_id, d.alert_type, d.detected_at, d.tags_changed_count,
            d.matched_mold_id, d.matched_machine_type_id, d.match_score,
            d.machine_type_mismatch, d.device_machine_type, d.sheet_machine_type,
            m.mold_code, m.mold_name, mt.machine_type AS matched_machine_type_name
        FROM dbo.mold_detection_alerts AS d
        LEFT JOIN dbo.molds AS m ON m.id = d.matched_mold_id
        LEFT JOIN dbo.mold_machine_types AS mt ON mt.id = d.matched_machine_type_id
        WHERE d.acknowledged_at IS NULL
        ORDER BY d.detected_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(parameter_sql)
            parameter_rows = [
                dict(warning_type="parameter", **_decorate(row_to_dict(cursor, row)))
                for row in cursor.fetchall()
            ]
            cursor.execute(output_sql)
            output_rows = [
                dict(warning_type="output", **row_to_dict(cursor, row))
                for row in cursor.fetchall()
            ]
            cursor.execute(detection_sql)
            detection_rows = []
            for row in cursor.fetchall():
                record = row_to_dict(cursor, row)
                # alert_type column already distinguishes "auto_assign"
                # from "unrecognized" -- reuse it directly as warning_type
                # instead of hardcoding one value like the other two kinds.
                record["warning_type"] = record.pop("alert_type")
                detection_rows.append(record)
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return sorted(
        parameter_rows + output_rows + detection_rows,
        key=lambda r: r["detected_at"],
        reverse=True,
    )


@router.post("/warnings/{warning_id}/clear")
def clear_warning(warning_id: int, user: dict = Depends(require_user)):
    """Clears a "parameter" warning specifically -- kept as the original
    unprefixed path for backward compatibility with existing links/
    bookmarks. Other warning types use their own prefixed clear routes
    (see clear_output_warning below) since ids aren't unique across
    warning types."""
    require_editor(user)
    sql = """
        UPDATE dbo.tech_parameter_changelog
        SET acknowledged_at = SYSUTCDATETIME(), acknowledged_by = ?
        WHERE id = ? AND acknowledged_at IS NULL
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, user["id"], warning_id)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="预警不存在或已清除")
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/warnings/output/{alert_id}/clear")
def clear_output_warning(alert_id: int, user: dict = Depends(require_user)):
    require_editor(user)
    sql = """
        UPDATE dbo.mold_output_alerts
        SET acknowledged_at = SYSUTCDATETIME(), acknowledged_by = ?
        WHERE id = ? AND acknowledged_at IS NULL
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, user["id"], alert_id)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="预警不存在或已清除")
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/warnings/detection/{alert_id}/clear")
def clear_detection_warning(alert_id: int, user: dict = Depends(require_user)):
    """Clears either kind of dbo.mold_detection_alerts row ('auto_assign'
    or 'unrecognized') -- they share one table and one id space, so one
    route (unlike clear_warning/clear_output_warning, which are split
    because 'parameter' kept its original unprefixed path for
    backward-compatible bookmarks)."""
    require_editor(user)
    sql = """
        UPDATE dbo.mold_detection_alerts
        SET acknowledged_at = SYSUTCDATETIME(), acknowledged_by = ?
        WHERE id = ? AND acknowledged_at IS NULL
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, user["id"], alert_id)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="预警不存在或已清除")
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/warnings/clear-all")
def clear_all_warnings(user: dict = Depends(require_user)):
    require_editor(user)
    parameter_sql = """
        UPDATE dbo.tech_parameter_changelog
        SET acknowledged_at = SYSUTCDATETIME(), acknowledged_by = ?
        WHERE acknowledged_at IS NULL
    """
    output_sql = """
        UPDATE dbo.mold_output_alerts
        SET acknowledged_at = SYSUTCDATETIME(), acknowledged_by = ?
        WHERE acknowledged_at IS NULL
    """
    detection_sql = """
        UPDATE dbo.mold_detection_alerts
        SET acknowledged_at = SYSUTCDATETIME(), acknowledged_by = ?
        WHERE acknowledged_at IS NULL
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(parameter_sql, user["id"])
            cleared = cursor.rowcount
            cursor.execute(output_sql, user["id"])
            cleared += cursor.rowcount
            cursor.execute(detection_sql, user["id"])
            cleared += cursor.rowcount
            connection.commit()
            return {"status": "ok", "cleared": cleared}
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error