USE [MES_MQTT];
GO

-- Latest 100 MQTT messages
SELECT TOP (100)
    id,
    device_id,
    data_type,
    data_time,
    mqtt_topic,
    data_json,
    received_at
FROM dbo.mqtt_messages
ORDER BY id DESC;

-- Number of messages by type
SELECT data_type, COUNT_BIG(*) AS message_count
FROM dbo.mqtt_messages
GROUP BY data_type
ORDER BY message_count DESC;


