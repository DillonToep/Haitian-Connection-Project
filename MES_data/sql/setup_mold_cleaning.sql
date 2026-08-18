USE MES_MQTT;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.molds') AND name = 'requires_cleaning'
)
BEGIN
    ALTER TABLE dbo.molds ADD requires_cleaning BIT NOT NULL DEFAULT 0;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.molds') AND name = 'cleaning_interval_hours'
)
BEGIN
    -- How often (in hours of production) the program should flag this
    -- mold's machine as due for a cleaning check.
    ALTER TABLE dbo.molds ADD cleaning_interval_hours DECIMAL(8,2) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.molds') AND name = 'cleaning_duration_minutes'
)
BEGIN
    -- Estimated time (minutes) the cleaning itself takes -- used for
    -- scheduling/downtime planning.
    ALTER TABLE dbo.molds ADD cleaning_duration_minutes INT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_molds_cleaning_interval'
)
BEGIN
    ALTER TABLE dbo.molds
        ADD CONSTRAINT CK_molds_cleaning_interval
            CHECK (cleaning_interval_hours IS NULL OR cleaning_interval_hours > 0);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_molds_cleaning_duration'
)
BEGIN
    ALTER TABLE dbo.molds
        ADD CONSTRAINT CK_molds_cleaning_duration
            CHECK (cleaning_duration_minutes IS NULL OR cleaning_duration_minutes > 0);
END;
GO