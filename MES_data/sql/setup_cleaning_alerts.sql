USE MES_MQTT;
GO
IF OBJECT_ID(N'dbo.cleaning_alerts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cleaning_alerts
    (
        id                      BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        device_id               NVARCHAR(100) NOT NULL,
        mold_id                 BIGINT NOT NULL,
        production_started_at  DATETIME2(3) NOT NULL,
        detected_at             DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        elapsed_minutes         INT NOT NULL,
        threshold_minutes       INT NOT NULL,
        acknowledged_at         DATETIME2(3) NULL,
        acknowledged_by         INT NULL,

        CONSTRAINT FK_cleaning_alerts_mold
            FOREIGN KEY (mold_id) REFERENCES dbo.molds(id),
        CONSTRAINT FK_cleaning_alerts_acknowledged_by
            FOREIGN KEY (acknowledged_by) REFERENCES dbo.app_users(id)
    );
    CREATE INDEX IX_cleaning_alerts_pending
        ON dbo.cleaning_alerts(device_id, production_started_at)
        WHERE acknowledged_at IS NULL;

    CREATE INDEX IX_cleaning_alerts_detected
        ON dbo.cleaning_alerts(detected_at DESC);
END;
GO