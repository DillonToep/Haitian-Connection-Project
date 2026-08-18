USE MES_MQTT;
GO

IF OBJECT_ID(N'dbo.mold_parameter_defaults', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_parameter_defaults
    (
        parameter_id      NVARCHAR(50) NOT NULL PRIMARY KEY,
        target_value      NVARCHAR(200) NULL,
        tolerance_mode    NVARCHAR(10) NOT NULL DEFAULT N'percent',
        tolerance_percent DECIMAL(12,4) NULL,
        tolerance_flat    DECIMAL(12,4) NULL,
        updated_at        DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_by        INT NULL,

        CONSTRAINT CK_mold_parameter_defaults_tolerance_mode
            CHECK (tolerance_mode IN (N'percent', N'flat')),
        CONSTRAINT FK_mold_parameter_defaults_updated_by
            FOREIGN KEY (updated_by) REFERENCES dbo.app_users(id)
    );
END;
GO