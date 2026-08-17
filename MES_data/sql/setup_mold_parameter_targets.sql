USE MES_MQTT;
GO

IF OBJECT_ID(N'dbo.mold_parameter_targets', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_parameter_targets
    (
        id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        mold_id             BIGINT NOT NULL,
        parameter_id        NVARCHAR(50) NOT NULL,
        target_value        NVARCHAR(200) NULL,
        tolerance_percent   DECIMAL(6,2) NULL,
        updated_at          DATETIME2(3) NOT NULL DEFAULT SYSDATETIME(),

        CONSTRAINT FK_mold_parameter_targets_mold
            FOREIGN KEY (mold_id) REFERENCES dbo.molds(id) ON DELETE CASCADE,
        CONSTRAINT UQ_mold_parameter_targets UNIQUE (mold_id, parameter_id),
        CONSTRAINT CK_mold_parameter_targets_tolerance
            CHECK (tolerance_percent IS NULL OR tolerance_percent >= 0)
    );

    CREATE INDEX IX_mold_parameter_targets_mold
        ON dbo.mold_parameter_targets(mold_id);
END;
GO