from contextlib import closing

import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from ..database import get_connection, row_to_dict
from ..parameter_labels import PARAMETER_LABELS, categorize
from ..security import require_user


router = APIRouter(prefix="/api", tags=["changelog"])


def _decorate(record: dict) -> dict:
    """Attach the human-readable label/category the frontend needs, using
    the same PARAMETER_LABELS dictionary the 工艺参数 tab is built from."""
    meta = PARAMETER_LABELS.get(record["parameter_id"])
    record["label"] = meta["label"] if meta else record["parameter_id"]
    record["category"] = categorize(record["label"])
    return record


@router.get("/changelog")
def get_changelog(user: dict = Depends(require_user)):
    del user
    sql = """
        SELECT TOP 500
            c.id, c.device_id, c.parameter_id, c.previous_value, c.new_value,
            c.data_time, c.detected_at, c.raw_message_id, c.spc_message_id
        FROM dbo.tech_parameter_changelog AS c
        ORDER BY c.detected_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [_decorate(row_to_dict(cursor, row)) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/changelog/by-device/{device_id}")
def get_changelog_for_device(device_id: str, user: dict = Depends(require_user)):
    """Same records as GET /api/changelog, filtered to one machine -- powers
    the 变更记录 tab inside the device detail view."""
    del user
    sql = """
        SELECT TOP 200
            c.id, c.device_id, c.parameter_id, c.previous_value, c.new_value,
            c.data_time, c.detected_at, c.raw_message_id, c.spc_message_id
        FROM dbo.tech_parameter_changelog AS c
        WHERE c.device_id = ?
        ORDER BY c.detected_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            return [_decorate(row_to_dict(cursor, row)) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/changelog/{changelog_id}")
def get_changelog_entry(changelog_id: int, user: dict = Depends(require_user)):
    del user
    sql = """
        SELECT
            c.id, c.device_id, c.parameter_id, c.previous_value, c.new_value,
            c.data_time, c.detected_at, c.raw_message_id, c.spc_message_id
        FROM dbo.tech_parameter_changelog AS c
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
    sql = """
        SELECT
            c.id, c.device_id, c.parameter_id, c.previous_value, c.new_value,
            c.data_time, c.detected_at, c.raw_message_id, c.spc_message_id
        FROM dbo.tech_parameter_changelog AS c
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