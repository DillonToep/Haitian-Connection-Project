USE MES_MQTT;
GO

-- mold_match_attempts: drop + recreate both FKs with ON DELETE SET NULL
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_mold_match_attempts_mold')
BEGIN
    ALTER TABLE dbo.mold_match_attempts DROP CONSTRAINT FK_mold_match_attempts_mold;
END;
GO
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_mold_match_attempts_machine_type')
BEGIN
    ALTER TABLE dbo.mold_match_attempts DROP CONSTRAINT FK_mold_match_attempts_machine_type;
END;
GO

ALTER TABLE dbo.mold_match_attempts
    ADD CONSTRAINT FK_mold_match_attempts_mold
        FOREIGN KEY (matched_mold_id) REFERENCES dbo.molds(id) ON DELETE SET NULL;
GO
ALTER TABLE dbo.mold_match_attempts
    ADD CONSTRAINT FK_mold_match_attempts_machine_type
        FOREIGN KEY (matched_machine_type_id) REFERENCES dbo.mold_machine_types(id) ON DELETE SET NULL;
GO

-- mold_detection_alerts: same latent issue, fix preemptively
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_mold_detection_alerts_mold')
BEGIN
    ALTER TABLE dbo.mold_detection_alerts DROP CONSTRAINT FK_mold_detection_alerts_mold;
END;
GO
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_mold_detection_alerts_machine_type')
BEGIN
    ALTER TABLE dbo.mold_detection_alerts DROP CONSTRAINT FK_mold_detection_alerts_machine_type;
END;
GO

ALTER TABLE dbo.mold_detection_alerts
    ADD CONSTRAINT FK_mold_detection_alerts_mold
        FOREIGN KEY (matched_mold_id) REFERENCES dbo.molds(id) ON DELETE SET NULL;
GO
ALTER TABLE dbo.mold_detection_alerts
    ADD CONSTRAINT FK_mold_detection_alerts_machine_type
        FOREIGN KEY (matched_machine_type_id) REFERENCES dbo.mold_machine_types(id) ON DELETE SET NULL;
GO