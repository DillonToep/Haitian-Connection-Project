USE MES_MQTT;
GO

IF OBJECT_ID(N'dbo.mold_extended_info', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_extended_info
    (
        mold_id     BIGINT NOT NULL PRIMARY KEY,
        info_json   NVARCHAR(MAX) NULL,
        updated_at  DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_by  INT NULL,

        CONSTRAINT FK_mold_extended_info_mold
            FOREIGN KEY (mold_id) REFERENCES dbo.molds(id) ON DELETE CASCADE,
        CONSTRAINT FK_mold_extended_info_user
            FOREIGN KEY (updated_by) REFERENCES dbo.app_users(id)
    );
END;
GO