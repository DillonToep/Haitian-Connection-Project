-- Auto Mold Detection & Assignment via MQTT Parameter Bursts.
--
-- See mqtt_monitor.py (_handle_burst / _find_best_mold_match /
-- _auto_assign_mold) for the detection + matching + assignment logic that
-- populates these tables, and backend/routers/warnings.py for how
-- dbo.mold_detection_alerts is merged into GET /api/warnings alongside the
-- existing "parameter" / "output" warning types.

USE MES_MQTT;
GO

-- ---------------------------------------------------------------------
-- dbo.mold_match_attempts -- lightweight audit trail of every burst
-- detection + matching attempt, whether or not it resulted in an
-- auto-assignment. This is what lets thresholds (BURST_CHANGE_THRESHOLD /
-- MATCH_CONFIDENCE_THRESHOLD / MIN_TARGETS_*) get tuned later against real
-- behavior, and lets a bad auto-assignment be investigated after the fact.
-- ---------------------------------------------------------------------
IF OBJECT_ID(N'dbo.mold_match_attempts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_match_attempts
    (
        id                          BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        device_id                   NVARCHAR(100) NOT NULL,
        detected_at                 DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        tags_changed_count          INT NOT NULL,
        raw_message_id              BIGINT NULL,
        matched_mold_id             BIGINT NULL,
        matched_machine_type_id     BIGINT NULL,
        match_score                 DECIMAL(5,4) NULL,
        outcome                     NVARCHAR(20) NOT NULL,

        CONSTRAINT CK_mold_match_attempts_outcome
            CHECK (outcome IN (N'assigned', N'no_match')),
        CONSTRAINT FK_mold_match_attempts_raw_message
            FOREIGN KEY (raw_message_id) REFERENCES dbo.mqtt_messages(id),
        CONSTRAINT FK_mold_match_attempts_mold
            FOREIGN KEY (matched_mold_id) REFERENCES dbo.molds(id),
        CONSTRAINT FK_mold_match_attempts_machine_type
            FOREIGN KEY (matched_machine_type_id) REFERENCES dbo.mold_machine_types(id)
    );

    CREATE INDEX IX_mold_match_attempts_device_time
        ON dbo.mold_match_attempts(device_id, detected_at DESC);
END;
GO

-- ---------------------------------------------------------------------
-- dbo.mold_detection_alerts -- the two new warning_types surfaced through
-- GET /api/warnings (see warnings.py): 'auto_assign' (a burst was matched
-- and the device was auto-assigned -- informational, not a confirmation
-- request, since auto-assignment is fully automatic) and 'unrecognized'
-- (a burst was detected but matched nothing above the confidence
-- threshold -- the assignment is left untouched). Same "unacknowledged
-- until cleared" shape as dbo.mold_output_alerts / dbo.cleaning_alerts,
-- but -- unlike those -- there is intentionally no uniqueness constraint
-- forcing one active alert per device: every distinct burst event is its
-- own alert row, since each is a separate, independently actionable event
-- (e.g. a device could get auto-assigned twice in a row to two different
-- molds and an operator should be able to see both).
-- ---------------------------------------------------------------------
IF OBJECT_ID(N'dbo.mold_detection_alerts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_detection_alerts
    (
        id                          BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        device_id                   NVARCHAR(100) NOT NULL,
        alert_type                  NVARCHAR(20) NOT NULL,
        detected_at                 DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        tags_changed_count          INT NOT NULL,

        -- Only populated for alert_type = 'auto_assign'.
        matched_mold_id             BIGINT NULL,
        matched_machine_type_id     BIGINT NULL,
        match_score                 DECIMAL(5,4) NULL,
        machine_type_mismatch       BIT NOT NULL DEFAULT 0,
        device_machine_type         NVARCHAR(150) NULL,
        sheet_machine_type          NVARCHAR(150) NULL,

        acknowledged_at             DATETIME2(3) NULL,
        acknowledged_by             INT NULL,

        CONSTRAINT CK_mold_detection_alerts_type
            CHECK (alert_type IN (N'auto_assign', N'unrecognized')),
        CONSTRAINT FK_mold_detection_alerts_mold
            FOREIGN KEY (matched_mold_id) REFERENCES dbo.molds(id),
        CONSTRAINT FK_mold_detection_alerts_machine_type
            FOREIGN KEY (matched_machine_type_id) REFERENCES dbo.mold_machine_types(id),
        CONSTRAINT FK_mold_detection_alerts_acknowledged_by
            FOREIGN KEY (acknowledged_by) REFERENCES dbo.app_users(id)
    );

    -- Fast lookup of still-pending detection alerts, used by GET /api/warnings.
    CREATE INDEX IX_mold_detection_alerts_pending
        ON dbo.mold_detection_alerts(detected_at DESC)
        WHERE acknowledged_at IS NULL;

    CREATE INDEX IX_mold_detection_alerts_device_time
        ON dbo.mold_detection_alerts(device_id, detected_at DESC);
END;
GO