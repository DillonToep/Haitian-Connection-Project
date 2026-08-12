-- 工艺参数 (process parameter) changelog table.
--
-- One row = one detected change of a single tech-parameter tag on a single
-- device. Rows are inserted in real time by mqtt_monitor.py as MQTT data
-- arrives (see _insert_changelog_rows in that file), and only for messages
-- whose gateway topic is "tech" -- see mqtt_monitor.py for why realtime/spc
-- messages are excluded even though some of their tags share names with
-- PARAMETER_LABELS entries.
--
-- spc_message_id starts out NULL: a parameter can change before the SPC
-- (cycle-summary) record for that production cycle exists yet. When the
-- next SPC/cycle message for the same device arrives (gateway topic
-- "spc"), every changelog row for that device that is still unclaimed
-- (spc_message_id IS NULL) is retro-assigned to that SPC message, because
-- it happened during the cycle that just completed. See
-- _assign_pending_changelogs_to_spc.
--
-- raw_message_id / spc_message_id both reference dbo.mqtt_messages.id
-- (confirmed BIGINT NOT NULL) -- see the FK constraint below.

USE MES_MQTT;
GO

IF OBJECT_ID(N'dbo.tech_parameter_changelog', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.tech_parameter_changelog
    (
        id              BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        device_id       NVARCHAR(100) NOT NULL,
        parameter_id    NVARCHAR(50) NOT NULL,
        previous_value  NVARCHAR(200) NULL,
        new_value       NVARCHAR(200) NULL,
        data_time       DATETIME2(3) NULL,
        detected_at     DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        raw_message_id  BIGINT NULL,
        spc_message_id  BIGINT NULL
    );

    CREATE INDEX IX_tech_changelog_device_time
        ON dbo.tech_parameter_changelog(device_id, detected_at DESC);

    -- Fast lookup of "still waiting for an SPC" rows for a device, used by
    -- _assign_pending_changelogs_to_spc every time a new SPC message arrives.
    CREATE INDEX IX_tech_changelog_pending_spc
        ON dbo.tech_parameter_changelog(device_id)
        WHERE spc_message_id IS NULL;

    CREATE INDEX IX_tech_changelog_spc
        ON dbo.tech_parameter_changelog(spc_message_id);
END;
GO

-- dbo.mqtt_messages.id is confirmed BIGINT NOT NULL, matching this table's
-- raw_message_id/spc_message_id columns, so the FK can be added safely.
IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_tech_changelog_raw_message'
)
BEGIN
    ALTER TABLE dbo.tech_parameter_changelog
        ADD CONSTRAINT FK_tech_changelog_raw_message
            FOREIGN KEY (raw_message_id) REFERENCES dbo.mqtt_messages(id);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_tech_changelog_spc_message'
)
BEGIN
    ALTER TABLE dbo.tech_parameter_changelog
        ADD CONSTRAINT FK_tech_changelog_spc_message
            FOREIGN KEY (spc_message_id) REFERENCES dbo.mqtt_messages(id);
END;
GO