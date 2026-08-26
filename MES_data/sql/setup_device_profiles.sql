USE MES_MQTT;
GO

IF OBJECT_ID(N'dbo.device_profiles', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.device_profiles
    (
        device_id       NVARCHAR(100) NOT NULL PRIMARY KEY,
        machine_type    NVARCHAR(150) NULL,
        updated_at      DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_by      INT NULL,

        CONSTRAINT FK_device_profiles_updated_by
            FOREIGN KEY (updated_by) REFERENCES dbo.app_users(id)
    );
END;
GO