from contextlib import closing

import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from ..database import get_connection, row_to_dict
from ..parameter_labels import (
    PARAMETER_LABELS,
    categorize_tag,
    ALARM_STATUS_LABELS,
    MACHINE_STATUS_LABELS,
    OPERATION_MODE_LABELS,
    label_status_code,
)
from ..security import require_user


router = APIRouter(prefix="/api", tags=["devices"])


def get_single_device_row(sql: str, device_id: str, missing_message: str):
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=missing_message)
            return row_to_dict(cursor, row)
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

def _decorate_status_labels(record: dict) -> dict:
    """Attach human-readable labels for STS/OPM/ASTS alongside their raw
    codes, so the frontend doesn't need to know the code tables itself."""
    if "machine_status" in record:
        record["machine_status_label"] = label_status_code(MACHINE_STATUS_LABELS, record.get("machine_status"))
    if "operation_mode" in record:
        record["operation_mode_label"] = label_status_code(OPERATION_MODE_LABELS, record.get("operation_mode"))
    if "alarm_status" in record:
        record["alarm_status_label"] = label_status_code(ALARM_STATUS_LABELS, record.get("alarm_status"))
    return record


@router.get("/devices")
def get_devices(user: dict = Depends(require_user)):
    del user
    sql = """
        WITH devices AS
        (
            SELECT DISTINCT device_id
            FROM dbo.mqtt_messages
            WHERE device_id IS NOT NULL AND device_id <> N''
        )
        SELECT
            d.device_id, a.id AS assignment_id, a.mounted_at,
            m.id AS mold_id, m.mold_code, m.mold_name,
            m.product_code, m.cavities
        FROM devices AS d
        LEFT JOIN dbo.device_mold_assignments AS a
            ON a.device_id = d.device_id AND a.unmounted_at IS NULL
        LEFT JOIN dbo.molds AS m ON m.id = a.mold_id
        ORDER BY d.device_id
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [row_to_dict(cursor, row) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/dashboard")
def get_dashboard(user: dict = Depends(require_user)):
    del user
    sql = """
        WITH devices AS
        (
            SELECT DISTINCT device_id
            FROM dbo.mqtt_messages
            WHERE device_id IS NOT NULL AND device_id <> N''
        ),
        latest_realtime AS
        (
            SELECT *, ROW_NUMBER() OVER
            (
                PARTITION BY device_id
                ORDER BY data_time DESC, raw_message_id DESC
            ) AS row_number
            FROM dbo.vw_machine_realtime
        ),
        latest_spc AS
        (
            SELECT *, ROW_NUMBER() OVER
            (
                PARTITION BY device_id
                ORDER BY data_time DESC, raw_message_id DESC
            ) AS row_number
            FROM dbo.vw_machine_spc
        )
        SELECT
            d.device_id, r.data_time, r.received_at,
            r.alarm_status, r.operation_mode,
            r.operation_time AS oil_temperature, r.machine_status,
            s.cycle_number, s.cycle_time,
            m.id AS mold_id, m.mold_code, m.mold_name,
            m.product_code, m.cavities, a.mounted_at
        FROM devices AS d
        LEFT JOIN latest_realtime AS r
            ON r.device_id = d.device_id AND r.row_number = 1
        LEFT JOIN latest_spc AS s
            ON s.device_id = d.device_id AND s.row_number = 1
        LEFT JOIN dbo.device_mold_assignments AS a
            ON a.device_id = d.device_id AND a.unmounted_at IS NULL
        LEFT JOIN dbo.molds AS m ON m.id = a.mold_id
        ORDER BY d.device_id
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [_decorate_status_labels(row_to_dict(cursor, row)) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/realtime")
def get_all_realtime(user: dict = Depends(require_user)):
    del user
    sql = """
        WITH latest_data AS
        (
            SELECT *, ROW_NUMBER() OVER
            (
                PARTITION BY device_id
                ORDER BY data_time DESC, raw_message_id DESC
            ) AS row_number
            FROM dbo.vw_machine_realtime
        )
        SELECT
            raw_message_id, device_id, data_time,
            alarm_status, operation_mode,
            operation_time AS oil_temperature, machine_status,
            temperature_1, temperature_2, temperature_3,
            temperature_4, temperature_5, temperature_6, temperature_7,
            received_at
        FROM latest_data
        WHERE row_number = 1
        ORDER BY device_id
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [_decorate_status_labels(row_to_dict(cursor, row)) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/realtime/{device_id}")
def get_device_realtime(device_id: str, user: dict = Depends(require_user)):
    del user
    sql = """
        SELECT TOP 1
            raw_message_id, device_id, data_time,
            alarm_status, operation_mode,
            operation_time AS oil_temperature, machine_status,
            temperature_1, temperature_2, temperature_3,
            temperature_4, temperature_5, temperature_6, temperature_7,
            received_at
        FROM dbo.vw_machine_realtime
        WHERE device_id = ?
        ORDER BY data_time DESC, raw_message_id DESC
    """
    return _decorate_status_labels(get_single_device_row(sql, device_id, "没有找到该设备的实时数据"))


@router.get("/tech/{device_id}")
def get_device_tech(device_id: str, user: dict = Depends(require_user)):
    del user
    sql = """
        WITH latest AS
        (
            SELECT MAX(raw_message_id) AS raw_message_id
            FROM dbo.vw_machine_tech
            WHERE device_id = ?
        )
        SELECT
            t.raw_message_id, t.device_id, t.data_time,
            t.parameter_id, t.parameter_value_text, t.parameter_value
        FROM dbo.vw_machine_tech AS t
        INNER JOIN latest AS l ON t.raw_message_id = l.raw_message_id
        ORDER BY t.parameter_id
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            rows = cursor.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="没有找到该设备的工艺参数")
            records = [row_to_dict(cursor, row) for row in rows]

            parameters = []
            for record in records:
                tag_id = record["parameter_id"]
                meta = PARAMETER_LABELS.get(tag_id)

                # Tag not in the label file: still show it (fail open) so new
                # or unmapped tags aren't silently lost, but flag it clearly.
                if meta is None:
                    parameters.append(
                        {
                            "parameter_id": tag_id,
                            "label": tag_id,
                            "category": "未知参数",
                            "value": record["parameter_value"]
                            if record["parameter_value"] is not None
                            else record["parameter_value_text"],
                            "raw_value": record["parameter_value"],
                        }
                    )
                    continue

                if not meta["use"]:
                    continue

                parameters.append(
                    {
                        "parameter_id": tag_id,
                        "label": meta["label"],
                        "category": categorize_tag(tag_id, meta["label"]),
                        "value": record["parameter_value"]
                        if record["parameter_value"] is not None
                        else record["parameter_value_text"],
                        "raw_value": record["parameter_value"],
                    }
                )

            return {
                "device_id": device_id,
                "raw_message_id": records[0]["raw_message_id"],
                "data_time": records[0]["data_time"],
                "parameters": parameters,
            }
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/spc/{device_id}")
def get_device_spc(device_id: str, user: dict = Depends(require_user)):
    del user
    sql = """
        SELECT TOP 1 *
        FROM dbo.vw_machine_spc
        WHERE device_id = ?
        ORDER BY data_time DESC, raw_message_id DESC
    """
    return get_single_device_row(sql, device_id, "没有找到该设备的 SPC 数据")