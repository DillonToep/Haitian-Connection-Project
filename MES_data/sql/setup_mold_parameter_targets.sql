USE MES_MQTT;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.mold_parameter_targets') AND name = 'tolerance_mode'
)
BEGIN
    ALTER TABLE dbo.mold_parameter_targets ADD tolerance_mode NVARCHAR(10) NOT NULL DEFAULT N'percent';
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.mold_parameter_targets') AND name = 'tolerance_flat'
)
BEGIN
    ALTER TABLE dbo.mold_parameter_targets ADD tolerance_flat DECIMAL(12,4) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_mold_parameter_targets_tolerance_mode'
)
BEGIN
    ALTER TABLE dbo.mold_parameter_targets
        ADD CONSTRAINT CK_mold_parameter_targets_tolerance_mode
            CHECK (tolerance_mode IN (N'percent', N'flat'));
END;
GO