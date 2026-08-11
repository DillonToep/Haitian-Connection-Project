import json
import logging
import os
from datetime import datetime

import paho.mqtt.client as mqtt
import pyodbc


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
    """将一条 MQTT 消息写入 SQL Server。"""
    global sql_connection

    data = payload.get("Data")

    data_json = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":")
    ) if data is not None else None

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
        payload.get("devId"),
        payload.get("topic"),
        parse_time(payload.get("sendTime")),
        payload.get("sendStamp"),
        parse_time(payload.get("time")),
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
            sql_connection.commit()

            return row[0]

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