from contextlib import closing

import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from ..database import get_connection, row_to_dict
from ..parameter_labels import PARAMETER_LABELS, categorize
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


def apply_scale(raw_value, scale: float):
    """Convert a raw SQL numeric value into its true engineering value.

    raw SQL value * scale = displayed value (e.g. a raw 2350 with
    scale 0.1 displays as 235.0).
    """
    if raw_value is None:
        return None
    try:
        return round(float(raw_value) * scale, 4)
    except (TypeError, ValueError):
        return raw_value


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
            rows = [row_to_dict(cursor, row) for row in cursor.fetchall()]
            for row in rows:
                if "oil_temperature" in row:
                    meta = PARAMETER_LABELS.get("OT")
                    if meta:
                        row["oil_temperature"] = apply_scale(row["oil_temperature"], meta["scale"])
                if "cycle_time" in row:
                    meta = PARAMETER_LABELS.get("ECYCT")
                    if meta:
                        row["cycle_time"] = apply_scale(row["cycle_time"], meta["scale"])
            return rows
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
            rows = [row_to_dict(cursor, row) for row in cursor.fetchall()]
            return [_scale_realtime_row(row) for row in rows]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


# Raw tag codes behind each realtime column, so we can look up label/scale/use.
_REALTIME_TAGS = {
    "machine_status": "STS",
    "operation_mode": "OPM",
    "alarm_status": "ASTS",
    "oil_temperature": "OT",
    "temperature_1": "T1",
    "temperature_2": "T2",
    "temperature_3": "T3",
    "temperature_4": "T4",
    "temperature_5": "T5",
    "temperature_6": "T6",
    "temperature_7": "T7",
}


def _scale_realtime_row(row: dict) -> dict:
    for column, tag_id in _REALTIME_TAGS.items():
        if column not in row:
            continue
        meta = PARAMETER_LABELS.get(tag_id)
        if meta:
            row[column] = apply_scale(row[column], meta["scale"])
    return row


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
    row = get_single_device_row(sql, device_id, "没有找到该设备的实时数据")
    return _scale_realtime_row(row)


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
                        "category": categorize(meta["label"]),
                        "value": apply_scale(record["parameter_value"], meta["scale"])
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
    row = get_single_device_row(sql, device_id, "没有找到该设备的 SPC 数据")

    # vw_machine_spc columns are named per-field (e.g. cycle_time); scale
    # them against the matching raw tag from the label file where we know
    # the mapping between the SQL column and the raw tag code.
    for column, tag_id in _SPC_TAGS.items():
        if column in row:
            meta = PARAMETER_LABELS.get(tag_id)
            if meta:
                row[column] = apply_scale(row[column], meta["scale"])
    return row


# Best-effort mapping from vw_machine_spc's named columns to the raw tag
# codes in the label file, so we can apply the correct scale factor.
# Columns not listed here are passed straight through unscaled.
_SPC_TAGS = {
    "cycle_number": "CYCN",
    "cycle_time": "ECYCT",
    "eject_time": "EEJET",
    "injection_max_pressure": "EIPM",
    "injection_end_position": "EIPSE",
    "injection_time": "EIPT",
    "injection_start_position": "EISS",
    "injection_max_speed": "EIVM",
    "mold_close_time": "EMCT",
    "mold_open_time": "EMOT",
    "switch_pressure": "ESIPP",
    "switch_position": "ESIPS",
    "switch_time": "ESIPT",
    "temperature_1": "ET1",
    "temperature_2": "ET2",
    "temperature_3": "ET3",
    "temperature_4": "ET4",
    "temperature_5": "ET5",
    "temperature_6": "ET6",
    "temperature_7": "ET7",
    "plasticizing_time": "EPLST",
    "plasticizing_max_pressure": "EPLSPM",
    "pickup_time": "EFCHT",
    "low_pressure_time": "EMCLP",
    "high_pressure_time": "EMCHP",
    "screw_retract_time": "ESB2T",
    "oil_temperature": "EOT",
}
