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
from ..security import require_editor, require_user


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
            s.cycle_time,
            CASE
                WHEN s.cycle_number IS NULL THEN NULL
                WHEN s.cycle_number - ISNULL(c.reset_cycle_number, 0) < 0 THEN 0
                ELSE s.cycle_number - ISNULL(c.reset_cycle_number, 0)
            END AS cycle_count_display,
            m.id AS mold_id, m.mold_code, m.mold_name,
            m.product_code, m.cavities, a.mounted_at
        FROM devices AS d
        LEFT JOIN latest_realtime AS r
            ON r.device_id = d.device_id AND r.row_number = 1
        LEFT JOIN latest_spc AS s
            ON s.device_id = d.device_id AND s.row_number = 1
        LEFT JOIN dbo.device_cycle_resets AS c
            ON c.device_id = d.device_id
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
    sql_realtime = """
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
    sql_cycle = """
        SELECT TOP 1 cycle_number
        FROM dbo.vw_machine_spc
        WHERE device_id = ?
        ORDER BY data_time DESC, raw_message_id DESC
    """
    sql_reset = """
        SELECT reset_cycle_number, reset_at
        FROM dbo.device_cycle_resets
        WHERE device_id = ?
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql_realtime, device_id)
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="没有找到该设备的实时数据")
            record = row_to_dict(cursor, row)

            cursor.execute(sql_cycle, device_id)
            cycle_row = cursor.fetchone()
            record["cycle_number"] = cycle_row.cycle_number if cycle_row else None

            cursor.execute(sql_reset, device_id)
            reset_row = cursor.fetchone()
            baseline = reset_row.reset_cycle_number if reset_row else 0
            record["cycle_reset_at"] = reset_row.reset_at if reset_row else None
            record["cycle_count_display"] = (
                max(record["cycle_number"] - baseline, 0)
                if record["cycle_number"] is not None else None
            )
            return _decorate_status_labels(record)
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/devices/{device_id}/cycle-count/reset")
def reset_cycle_count(device_id: str, user: dict = Depends(require_user)):
    """Zero out the displayed 模次 tile AND the currently-mounted mold's
    production counters (今日/本周/累计产量, plus its max_output alert
    baseline) in one action. This is a full "start a new count" reset for
    the device's current run -- the machine's raw CYCN value itself is
    never touched, only our own derived counters."""
    require_editor(user)
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
    sql_current_mold = """
        SELECT m.id AS mold_id
        FROM dbo.device_mold_assignments AS a
        INNER JOIN dbo.molds AS m ON m.id = a.mold_id
        WHERE a.device_id = ? AND a.unmounted_at IS NULL
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()

            cursor.execute(sql_latest_cycle, device_id)
            row = cursor.fetchone()
            baseline = row.cycle_number if row and row.cycle_number is not None else 0
            cursor.execute(sql_upsert_cycle, device_id, baseline, user["id"], baseline, user["id"])

            cursor.execute(sql_current_mold, device_id)
            mold_row = cursor.fetchone()
            if mold_row is not None:
                mold_id = mold_row.mold_id
                # 今日 / 本周产量 are COUNT(*) rollups over this table --
                # wiping the log for this mold zeroes both in one step.
                cursor.execute("DELETE FROM dbo.mold_production_log WHERE mold_id = ?", mold_id)
                cursor.execute("UPDATE dbo.molds SET total_output = 0 WHERE id = ?", mold_id)
                # A pending 产量超限 alert no longer reflects reality once
                # total_output is back to 0 -- clear it so it doesn't sit
                # around stale until production climbs past max_output again.
                cursor.execute(
                    "DELETE FROM dbo.mold_output_alerts WHERE mold_id = ? AND acknowledged_at IS NULL",
                    mold_id,
                )

            connection.commit()
            return {"status": "ok", "reset_cycle_number": baseline}
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


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


@router.delete("/devices/{device_id}")
def delete_device(device_id: str, user: dict = Depends(require_user)):
    """Permanently remove a machine and every record tied to its
    device_id -- raw MQTT messages, 工艺参数 changelog rows, mold
    装卸 history, and any pending cleaning alerts. Devices aren't a real
    table (they're just distinct device_id values seen in
    dbo.mqtt_messages), so "deleting a machine" means purging all of its
    stored data; once the last mqtt_messages row for a device_id is gone
    it stops appearing on the dashboard / device list entirely. This
    cannot be undone.

    Order matters for FK safety: tech_parameter_changelog rows reference
    dbo.mqtt_messages(id) (see setup_changelog.sql), so they're deleted
    before the mqtt_messages rows themselves. cleaning_alerts and
    device_mold_assignments key off device_id directly and have no such
    dependency, so their order relative to the others doesn't matter.
    """
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()

            exists = cursor.execute(
                "SELECT TOP 1 1 FROM dbo.mqtt_messages WHERE device_id = ?",
                device_id,
            ).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="设备不存在")

            cursor.execute(
                "DELETE FROM dbo.tech_parameter_changelog WHERE device_id = ?",
                device_id,
            )
            cursor.execute(
                "DELETE FROM dbo.cleaning_alerts WHERE device_id = ?",
                device_id,
            )
            cursor.execute(
                "DELETE FROM dbo.device_mold_assignments WHERE device_id = ?",
                device_id,
            )
            cursor.execute(
                "DELETE FROM dbo.mqtt_messages WHERE device_id = ?",
                device_id,
            )
            cursor.execute(
                "MERGE dbo.deleted_devices AS target "
                "USING (SELECT ? AS device_id) AS src ON target.device_id = src.device_id "
                "WHEN NOT MATCHED THEN INSERT (device_id) VALUES (src.device_id);",
                device_id,
            )

            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error