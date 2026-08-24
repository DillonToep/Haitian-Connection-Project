USE MES_MQTT;
GO

IF OBJECT_ID(N'dbo.device_cycle_resets', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.device_cycle_resets
    (
        device_id           NVARCHAR(100) NOT NULL PRIMARY KEY,
        reset_cycle_number  BIGINT NOT NULL DEFAULT 0,
        reset_at            DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        reset_by            INT NULL,

        CONSTRAINT FK_device_cycle_resets_user
            FOREIGN KEY (reset_by) REFERENCES dbo.app_users(id)
    );
END;
GO