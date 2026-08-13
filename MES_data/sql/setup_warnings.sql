USE MES_MQTT;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.tech_parameter_changelog') AND name = 'acknowledged_at'
)
BEGIN
    ALTER TABLE dbo.tech_parameter_changelog ADD acknowledged_at DATETIME2(3) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.tech_parameter_changelog') AND name = 'acknowledged_by'
)
BEGIN
    ALTER TABLE dbo.tech_parameter_changelog ADD acknowledged_by INT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_tech_changelog_acknowledged_by'
)
BEGIN
    ALTER TABLE dbo.tech_parameter_changelog
        ADD CONSTRAINT FK_tech_changelog_acknowledged_by
            FOREIGN KEY (acknowledged_by) REFERENCES dbo.app_users(id);
END;
GO

-- Fast lookup of "still-pending" warnings, used by GET /api/warnings.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_tech_changelog_unacknowledged'
      AND object_id = OBJECT_ID(N'dbo.tech_parameter_changelog')
)
BEGIN
    CREATE INDEX IX_tech_changelog_unacknowledged
        ON dbo.tech_parameter_changelog(detected_at DESC)
        WHERE acknowledged_at IS NULL;
END;
GO