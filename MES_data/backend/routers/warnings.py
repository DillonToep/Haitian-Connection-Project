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
    """Pending (unacknowledged) parameter-change warnings, newest first.
    A warning is just a changelog row that hasn't been cleared yet."""
    del user
    sql = """
        SELECT TOP 200
            c.id, c.device_id, c.parameter_id, c.previous_value, c.new_value,
            c.data_time, c.detected_at, c.raw_message_id, c.spc_message_id,
            s.cycle_number AS spc_cycle_number
        FROM dbo.tech_parameter_changelog AS c
        LEFT JOIN dbo.vw_machine_spc AS s ON s.raw_message_id = c.spc_message_id
        WHERE c.acknowledged_at IS NULL
        ORDER BY c.detected_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [_decorate(row_to_dict(cursor, row)) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/warnings/{warning_id}/clear")
def clear_warning(warning_id: int, user: dict = Depends(require_user)):
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


@router.post("/warnings/clear-all")
def clear_all_warnings(user: dict = Depends(require_user)):
    require_editor(user)
    sql = """
        UPDATE dbo.tech_parameter_changelog
        SET acknowledged_at = SYSUTCDATETIME(), acknowledged_by = ?
        WHERE acknowledged_at IS NULL
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, user["id"])
            cleared = cursor.rowcount
            connection.commit()
            return {"status": "ok", "cleared": cleared}
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error