import json
import logging
import os
from contextlib import closing
from datetime import datetime, timedelta

import paho.mqtt.client as mqtt
import pyodbc

from backend.parameter_labels import PARAMETER_LABELS


# ================= MQTT 配置 =================

MQTT_HOST = "192.168.1.9"
MQTT_PORT = 1883
MQTT_USERNAME = "mqttadmin"
MQTT_PASSWORD = "Mqttadmin@123"
MQTT_SUB_TOPIC = "#"
MQTT_CLIENT_ID = "mes_sql_collector_v2"


# ================= SQL Server 配置 =================

SQL_CONNECTION_STRING = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    r"SERVER=localhost\SQLDEVELOP;"
    "DATABASE=MES_MQTT;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

sql_connection = None

CHANGELOG_TAGS = set(PARAMETER_LABELS.keys())

_last_values: dict[str, dict[str, str]] = {}
_last_machine_status: dict[str, int] = {}

# Device ids that have been permanently deleted via the web UI (DELETE
# /api/devices/{device_id}). Loaded once at startup from
# dbo.deleted_devices and consulted on every incoming message so a device
# never "comes back" just because the broker redelivers a retained
# message, or the physical machine is still publishing, after it was
# deleted in the app.
_deleted_devices: set[str] = set()

TECH_MESSAGE_TOPIC = "tech"
SPC_MESSAGE_TOPIC = "spc"
REALTIME_MESSAGE_TOPIC = "realtime"
ACTIVE_MACHINE_STATUS = 2


def _stringify(value):
    """Normalize a raw tag value to a string for comparison/storage.
    Returns None for values we can't meaningfully diff (missing, nested
    objects/arrays)."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    return str(value)


def _detect_parameter_changes(device_id, data):
    """Compare incoming tag values in `data` against the last known values
    for this device. Returns a list of (parameter_id, previous_value,
    new_value) tuples for every 工艺参数 tag whose value actually changed.
    """
    if not device_id or not isinstance(data, dict):
        return []

    device_cache = _last_values.setdefault(device_id, {})
    changes = []

    for tag, raw_value in data.items():
        if tag not in CHANGELOG_TAGS:
            continue

        new_value = _stringify(raw_value)
        if new_value is None:
            continue

        previous_value = device_cache.get(tag)
        if previous_value is None:
            # First time we've seen this tag for this device this run --
            # nothing to compare against, so just seed the cache.
            device_cache[tag] = new_value
            continue

        if previous_value != new_value:
            changes.append((tag, previous_value, new_value))
            device_cache[tag] = new_value

    return changes

def _fetch_mold_targets(cursor, device_id):
    """Tolerance targets come from the mold's MAIN 机型 specification
    record (Mold -> Machine Type -> Specifications). Each machine type
    holds its own independent set of targets (see
    setup_mold_machine_types.sql); is_main = 1 marks the one machine type
    that drives notifications/tolerance checking for this mold."""
    cursor.execute(
        """
        SELECT t.parameter_id, t.target_value, t.tolerance_mode, t.tolerance_percent, t.tolerance_flat
        FROM dbo.device_mold_assignments AS a
        INNER JOIN dbo.mold_machine_types AS mt ON mt.mold_id = a.mold_id AND mt.is_main = 1
        INNER JOIN dbo.mold_parameter_targets AS t ON t.machine_type_id = mt.id
        WHERE a.device_id = ? AND a.unmounted_at IS NULL
        """,
        device_id,
    )
    return {
        row.parameter_id: (row.target_value, row.tolerance_mode, row.tolerance_percent, row.tolerance_flat)
        for row in cursor.fetchall()
    }


def _exceeds_tolerance(new_value, target_value, tolerance_mode, tolerance_percent, tolerance_flat):
    """True if new_value deviates from target_value by more than the
    configured tolerance -- a percentage of target_value in 'percent'
    mode, or a flat absolute amount in 'flat' mode. Anything that can't
    be compared numerically never counts as a violation."""
    if target_value is None:
        return False
    try:
        new_num = float(new_value)
        target_num = float(target_value)
    except (TypeError, ValueError):
        return False

    if tolerance_mode == "flat":
        if tolerance_flat is None:
            return False
        try:
            tol_num = float(tolerance_flat)
        except (TypeError, ValueError):
            return False
        return abs(new_num - target_num) > tol_num

    # percent mode (default / back-compat)
    if tolerance_percent is None:
        return False
    try:
        tol_num = float(tolerance_percent)
    except (TypeError, ValueError):
        return False

    if target_num == 0:
        return abs(new_num) > tol_num
    return abs(new_num - target_num) / abs(target_num) * 100 > tol_num


def _record_production_and_check_output(cursor, device_id, spc_message_id, data_time):
    """Called once per SPC (cycle-complete) message. Attributes the cycle
    to whatever mold is currently mounted on this device, bumps its
    lifetime counter, and raises/refreshes an output alert if it just
    crossed max_output."""
    row = cursor.execute(
        """
        SELECT a.id AS assignment_id, m.id AS mold_id, m.max_output
        FROM dbo.device_mold_assignments AS a
        INNER JOIN dbo.molds AS m ON m.id = a.mold_id
        WHERE a.device_id = ? AND a.unmounted_at IS NULL
        """,
        device_id,
    ).fetchone()
    if row is None:
        return  # nothing mounted -- nothing to attribute this cycle to

    cursor.execute(
        """
        INSERT INTO dbo.mold_production_log
            (mold_id, device_id, assignment_id, produced_at, raw_message_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        row.mold_id, device_id, row.assignment_id, data_time, spc_message_id,
    )

    new_total = cursor.execute(
        """
        UPDATE dbo.molds SET total_output = total_output + 1
        OUTPUT INSERTED.total_output
        WHERE id = ?
        """,
        row.mold_id,
    ).fetchone()[0]

    if row.max_output is not None and new_total > row.max_output:
        cursor.execute(
            """
            IF NOT EXISTS (
                SELECT 1 FROM dbo.mold_output_alerts
                WHERE mold_id = ? AND acknowledged_at IS NULL
            )
            INSERT INTO dbo.mold_output_alerts (mold_id, device_id, total_output, max_output)
            VALUES (?, ?, ?, ?)
            """,
            row.mold_id, row.mold_id, device_id, new_total, row.max_output,
        )


def _insert_changelog_rows(cursor, device_id, changes, raw_message_id, data_time):
    if not changes:
        return

    mold_targets = _fetch_mold_targets(cursor, device_id)
    producing = _last_machine_status.get(device_id) == ACTIVE_MACHINE_STATUS

    sql = """
        INSERT INTO dbo.tech_parameter_changelog
        (
            device_id,
            parameter_id,
            previous_value,
            new_value,
            data_time,
            raw_message_id,
            acknowledged_at,
            during_production
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    for parameter_id, previous_value, new_value in changes:
        target = mold_targets.get(parameter_id)
        is_warning = False
        if target is not None:
            target_value, tolerance_mode, tolerance_percent, tolerance_flat = target
            is_warning = _exceeds_tolerance(new_value, target_value, tolerance_mode, tolerance_percent, tolerance_flat)
        acknowledged_at = None if is_warning else datetime.utcnow()

        cursor.execute(
            sql,
            device_id,
            parameter_id,
            previous_value,
            new_value,
            data_time,
            raw_message_id,
            acknowledged_at,
            1 if producing else 0,
        )

def _assign_pending_changelogs_to_spc(cursor, device_id, spc_message_id):
    cursor.execute(
        """
        UPDATE dbo.tech_parameter_changelog
        SET spc_message_id = ?
        WHERE device_id = ? AND spc_message_id IS NULL AND during_production = 1
        """,
        spc_message_id,
        device_id,
    )


def parse_time(value):
    """将网关时间字符串转换成 Python 时间。"""
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def connect_sql():
    """连接 SQL Server。"""
    global sql_connection

    sql_connection = pyodbc.connect(
        SQL_CONNECTION_STRING,
        autocommit=False
    )

    logging.info("SQL Server 连接成功")


def load_deleted_devices():
    """Populate _deleted_devices from dbo.deleted_devices. Called once at
    startup (after connect_sql()) so on_message can immediately start
    filtering, and can also be called again later (e.g. after deleting a
    new device while the collector is already running) to pick up
    changes without a restart."""
    global _deleted_devices

    with closing(sql_connection.cursor()) as cursor:
        cursor.execute("SELECT device_id FROM dbo.deleted_devices")
        _deleted_devices = {row[0] for row in cursor.fetchall()}

    logging.info("已加载 %d 个已删除设备", len(_deleted_devices))


def close_sql():
    global sql_connection

    if sql_connection is not None:
        try:
            sql_connection.close()
        except pyodbc.Error:
            pass

    sql_connection = None


def insert_message(message, payload, raw_payload):
    """将一条 MQTT 消息写入 SQL Server，并在同一事务中检测/记录 工艺参数 变更。"""
    global sql_connection

    device_id = payload.get("devId")
    if device_id in _deleted_devices:
        return None

    data = payload.get("Data")

    data = payload.get("Data")

    data_json = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":")
    ) if data is not None else None

    device_id = payload.get("devId")
    data_time = parse_time(payload.get("time"))
    topic = payload.get("topic")

    sql = """
        INSERT INTO dbo.mqtt_messages
        (
            mqtt_topic,
            mqtt_qos,
            is_retained,
            is_duplicate,
            client_id,
            device_id,
            data_type,
            send_time,
            send_timestamp,
            data_time,
            data_timestamp,
            data_json,
            payload_json
        )
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    values = (
        message.topic,
        message.qos,
        bool(message.retain),
        bool(message.dup),
        payload.get("clientId"),
        device_id,
        payload.get("topic"),
        parse_time(payload.get("sendTime")),
        payload.get("sendStamp"),
        data_time,
        payload.get("timestamp"),
        data_json,
        raw_payload
    )

    # 数据库断线时重新连接并重试一次
    for attempt in range(2):
        try:
            if sql_connection is None:
                connect_sql()

            cursor = sql_connection.cursor()
            row = cursor.execute(sql, values).fetchone()
            record_id = row[0]

            if device_id and topic == TECH_MESSAGE_TOPIC:
                changes = _detect_parameter_changes(device_id, data)
                _insert_changelog_rows(cursor, device_id, changes, record_id, data_time)

            if device_id and topic == REALTIME_MESSAGE_TOPIC and isinstance(data, dict):
                sts = data.get("STS")
                if sts is not None:
                    try:
                        _last_machine_status[device_id] = int(sts)
                    except (TypeError, ValueError):
                        pass

            if device_id and topic == SPC_MESSAGE_TOPIC:
                _assign_pending_changelogs_to_spc(cursor, device_id, record_id)
                _record_production_and_check_output(cursor, device_id, record_id, data_time)

            sql_connection.commit()

            return record_id

        except pyodbc.Error:
            close_sql()

            if attempt == 1:
                raise


def on_connect(client, userdata, flags, reason_code, properties):
    """MQTT 连接成功后订阅所有主题。"""
    if reason_code == 0:
        logging.info("MQTT 连接成功")

        client.subscribe(
            MQTT_SUB_TOPIC,
            qos=1
        )

        logging.info("已订阅：%s", MQTT_SUB_TOPIC)
    else:
        logging.error("MQTT 连接失败：%s", reason_code)


def on_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties
):
    logging.warning(
        "MQTT 连接断开：%s，等待自动重连",
        reason_code
    )


def on_subscribe(client, userdata, mid, reason_codes, properties):
    print("SUBACK reason codes:", reason_codes)


def on_message(client, userdata, message):
    """收到 MQTT 消息后解析并写入 SQL。"""
    print("RAW MESSAGE RECEIVED:", message.topic)
    try:
        raw_payload = message.payload.decode("utf-8")
        payload = json.loads(raw_payload)

        if not isinstance(payload, dict):
            raise ValueError("JSON 根节点不是对象")

        record_id = insert_message(
            message,
            payload,
            raw_payload
        )

        logging.info(
            "数据写入成功 ID=%s Device=%s Type=%s Time=%s",
            record_id,
            payload.get("devId"),
            payload.get("topic"),
            payload.get("time")
        )

    except json.JSONDecodeError:
        logging.exception(
            "收到的消息不是有效 JSON，Topic=%s",
            message.topic
        )

    except Exception:
        logging.exception(
            "消息处理失败，Topic=%s",
            message.topic
        )


def main():
    if not MQTT_PASSWORD:
        raise ValueError("尚未设置 MQTT_PASSWORD")

    # 程序启动时先测试数据库连接
    connect_sql()

    # 加载已删除设备名单，避免保留消息/仍在发送数据的设备被重新写入
    load_deleted_devices()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=MQTT_CLIENT_ID,
        clean_session=True
    )

    client.username_pw_set(
        MQTT_USERNAME,
        MQTT_PASSWORD
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.on_subscribe = on_subscribe

    client.reconnect_delay_set(
        min_delay=1,
        max_delay=30
    )

    logging.info(
        "正在连接 MQTT：%s:%s",
        MQTT_HOST,
        MQTT_PORT
    )

    try:
        client.connect(
            MQTT_HOST,
            MQTT_PORT,
            keepalive=60
        )

        client.loop_forever()

    except KeyboardInterrupt:
        logging.info("程序已停止")
        client.disconnect()

    finally:
        close_sql()


if __name__ == "__main__":
    main()