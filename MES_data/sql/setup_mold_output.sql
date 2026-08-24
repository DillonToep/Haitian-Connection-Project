USE MES_MQTT;
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.molds') AND name = 'max_output')
BEGIN
    ALTER TABLE dbo.molds ADD max_output INT NULL;
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.molds') AND name = 'total_output')
BEGIN
    ALTER TABLE dbo.molds ADD total_output BIGINT NOT NULL DEFAULT 0;
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_molds_max_output')
BEGIN
    ALTER TABLE dbo.molds
        ADD CONSTRAINT CK_molds_max_output CHECK (max_output IS NULL OR max_output > 0);
END;
GO

-- One row per completed cycle, attributed to whichever mold was mounted
-- on that device at the time (see _record_production_and_check_output in
-- mqtt_monitor.py). Powers the daily/weekly output rollups.
IF OBJECT_ID(N'dbo.mold_production_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_production_log
    (
        id              BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        mold_id         BIGINT NOT NULL,
        device_id       NVARCHAR(100) NOT NULL,
        assignment_id   BIGINT NULL,
        produced_at     DATETIME2(3) NOT NULL,
        raw_message_id  BIGINT NULL,

        CONSTRAINT FK_mold_prod_log_mold
            FOREIGN KEY (mold_id) REFERENCES dbo.molds(id),
        CONSTRAINT FK_mold_prod_log_assignment
            FOREIGN KEY (assignment_id) REFERENCES dbo.device_mold_assignments(id),
        CONSTRAINT FK_mold_prod_log_message
            FOREIGN KEY (raw_message_id) REFERENCES dbo.mqtt_messages(id)
    );

    CREATE INDEX IX_mold_prod_log_mold_time
        ON dbo.mold_production_log(mold_id, produced_at DESC);
    CREATE INDEX IX_mold_prod_log_device_time
        ON dbo.mold_production_log(device_id, produced_at DESC);
END;
GO

-- Output-limit warnings -- same "one active alert at a time" shape as
-- dbo.cleaning_alerts, so a mold that stays over its limit doesn't get a
-- new alert row inserted on every single subsequent cycle.
IF OBJECT_ID(N'dbo.mold_output_alerts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_output_alerts
    (
        id               BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        mold_id          BIGINT NOT NULL,
        device_id        NVARCHAR(100) NOT NULL,
        total_output     BIGINT NOT NULL,
        max_output       INT NOT NULL,
        detected_at      DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        acknowledged_at  DATETIME2(3) NULL,
        acknowledged_by  INT NULL,

        CONSTRAINT FK_mold_output_alerts_mold
            FOREIGN KEY (mold_id) REFERENCES dbo.molds(id),
        CONSTRAINT FK_mold_output_alerts_user
            FOREIGN KEY (acknowledged_by) REFERENCES dbo.app_users(id)
    );

    CREATE UNIQUE INDEX UX_mold_output_alerts_active
        ON dbo.mold_output_alerts(mold_id)
        WHERE acknowledged_at IS NULL;

    CREATE INDEX IX_mold_output_alerts_pending
        ON dbo.mold_output_alerts(detected_at DESC)
        WHERE acknowledged_at IS NULL;
END;
GO