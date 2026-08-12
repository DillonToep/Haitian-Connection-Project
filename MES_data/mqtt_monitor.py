import json
import logging
import os
from datetime import datetime

import paho.mqtt.client as mqtt
import pyodbc

from backend.parameter_labels import PARAMETER_LABELS


# ================= MQTT 配置 =================

MQTT_HOST = "192.168.72.173"
MQTT_PORT = 1883
MQTT_USERNAME = "mqttadmin"
MQTT_PASSWORD = "Mqttadmin@123"
MQTT_SUB_TOPIC = "#"
MQTT_CLIENT_ID = "mes_sql_collector"


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


# ================= 工艺参数变更记录 =================
#
# All raw tag codes that PARAMETER_LABELS knows about are treated as
# 工艺参数 (tech parameters) for changelog purposes -- this is the same
# dictionary backend/routers/devices.py uses to label the 工艺参数 tab, so
# "a tag the tech tab would show" and "a tag we track for changes" stay in
# sync automatically.
#
# IMPORTANT: PARAMETER_LABELS also contains tags that belong to the
# realtime (T1-T7, OT, STS, ASTS, OPM) and spc (CYCN, ECYCT, ET1-ET7,
# EIPM, ...) namespaces, because it doubles as the label source for those
# views too. Those tags legitimately change on every realtime tick (~10s)
# or every cycle (~60s) -- that's normal telemetry, not someone editing a
# 工艺参数/recipe setting. Change-detection is therefore only run against
# messages whose topic is "tech" (see insert_message below), mirroring
# vw_machine_tech's own "WHERE data_type = N'tech'" filter, so this tag
# set is never compared against realtime/spc payloads.
CHANGELOG_TAGS = set(PARAMETER_LABELS.keys())

# Cache of the last known value per (device_id -> {parameter_id: value}).
# It only lives in this process's memory: on a fresh start there is nothing
# to compare the first message against yet, so the first value seen for
# each tag after a restart is cached but not reported as a "change". This
# avoids manufacturing a false changelog entry every time the collector
# restarts.
_last_values: dict[str, dict[str, str]] = {}

# The gateway payload's own "topic" field (stored as mqtt_messages.data_type)
# already flags what kind of message this is -- "tech", "spc", "realtime",
# "wm", "opMode", "opLog". Use those values directly rather than sniffing
# for a specific tag (e.g. CYCN) inside Data.
TECH_MESSAGE_TOPIC = "tech"
SPC_MESSAGE_TOPIC = "spc"


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


def _insert_changelog_rows(cursor, device_id, changes, raw_message_id, data_time):
    """Insert one dbo.tech_parameter_changelog row per detected change,
    within the caller's existing transaction (committed together with the
    raw message insert)."""
    if not changes:
        return

    sql = """
        INSERT INTO dbo.tech_parameter_changelog
        (
            device_id,
            parameter_id,
            previous_value,
            new_value,
            data_time,
            raw_message_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """

    for parameter_id, previous_value, new_value in changes:
        cursor.execute(
            sql,
            device_id,
            parameter_id,
            previous_value,
            new_value,
            data_time,
            raw_message_id
        )


def _assign_pending_changelogs_to_spc(cursor, device_id, spc_message_id):
    """Claim every changelog row for this device that hasn't been
    associated with an SPC yet, now that one exists. Individual changelog
    rows are never merged or overwritten -- this only fills in
    spc_message_id, so the full history of changes leading up to the SPC
    is preserved (see README/task requirements: "Do not overwrite previous
    changelog entries")."""
    cursor.execute(
        """
        UPDATE dbo.tech_parameter_changelog
        SET spc_message_id = ?
        WHERE device_id = ? AND spc_message_id IS NULL
        """,
        spc_message_id,
        device_id
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

            # ---- 工艺参数变更记录：在同一事务内完成，不干扰原有写入流程 ----
            # Only "tech" messages carry 工艺参数/recipe settings -- realtime
            # and spc messages reuse some of the same tag names (T1, CYCN,
            # ET1, ...) for fast-changing telemetry that would otherwise
            # flood the changelog with false "changes" every few seconds.
            if device_id and topic == TECH_MESSAGE_TOPIC:
                changes = _detect_parameter_changes(device_id, data)
                _insert_changelog_rows(cursor, device_id, changes, record_id, data_time)

            # A message explicitly flagged as "spc" is a completed
            # cycle-summary record -- claim every not-yet-claimed changelog
            # row for this device into it, since those changes happened
            # during the cycle that just finished.
            if device_id and topic == SPC_MESSAGE_TOPIC:
                _assign_pending_changelogs_to_spc(cursor, device_id, record_id)

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


def on_message(client, userdata, message):
    """收到 MQTT 消息后解析并写入 SQL。"""
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

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=MQTT_CLIENT_ID,
        clean_session=False
    )

    client.username_pw_set(
        MQTT_USERNAME,
        MQTT_PASSWORD
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

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