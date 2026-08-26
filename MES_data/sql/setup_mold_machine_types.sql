-- Adds a "机型" (machine type) layer between a mold and its specifications:
--   Mold -> Machine Type -> Specifications
--
-- Previously dbo.mold_parameter_targets / dbo.mold_extended_info were keyed
-- directly by mold_id (one specification set per mold). This migration
-- introduces dbo.mold_machine_types and re-keys both tables to
-- machine_type_id, so the same mold can hold one independent specification
-- set per 机型.
--
-- Existing data is preserved: every mold that already has parameter
-- targets and/or extended info gets one auto-created "默认机型" machine
-- type (flagged as the mold's main machine type), and all of its existing
-- rows are backfilled to point at that new machine type. Nothing is
-- deleted or overwritten.

USE MES_MQTT;
GO

-- ---------------------------------------------------------------------
-- 1. dbo.mold_machine_types
-- ---------------------------------------------------------------------
IF OBJECT_ID(N'dbo.mold_machine_types', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_machine_types
    (
        id              BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        mold_id         BIGINT NOT NULL,
        machine_type    NVARCHAR(150) NOT NULL,   -- 机型, e.g. "MA5300/3200GIII"
        is_main         BIT NOT NULL DEFAULT 0,   -- drives notification/tolerance hookup
        created_at      DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        created_by      INT NULL,

        CONSTRAINT FK_mold_machine_types_mold
            FOREIGN KEY (mold_id) REFERENCES dbo.molds(id) ON DELETE CASCADE,
        CONSTRAINT FK_mold_machine_types_created_by
            FOREIGN KEY (created_by) REFERENCES dbo.app_users(id)
    );

    CREATE INDEX IX_mold_machine_types_mold
        ON dbo.mold_machine_types(mold_id);

    -- At most one "main" machine type per mold -- this is the one
    -- mqtt_monitor.py checks tolerances against / raises warnings for.
    CREATE UNIQUE INDEX UX_mold_machine_types_main
        ON dbo.mold_machine_types(mold_id)
        WHERE is_main = 1;
END;
GO

-- ---------------------------------------------------------------------
-- 2. Re-key dbo.mold_parameter_targets: mold_id -> machine_type_id
--    mold_id is relaxed to NULL-able: new rows are written keyed only by
--    machine_type_id (see molds.py), and the FK to mold_machine_types is
--    what enforces the mold relationship going forward.
-- ---------------------------------------------------------------------
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.mold_parameter_targets') AND name = 'mold_id' AND is_nullable = 0
)
BEGIN
    ALTER TABLE dbo.mold_parameter_targets ALTER COLUMN mold_id BIGINT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.mold_parameter_targets') AND name = 'machine_type_id'
)
BEGIN
    ALTER TABLE dbo.mold_parameter_targets ADD machine_type_id BIGINT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_mold_parameter_targets_machine_type'
)
BEGIN
    ALTER TABLE dbo.mold_parameter_targets
        ADD CONSTRAINT FK_mold_parameter_targets_machine_type
            FOREIGN KEY (machine_type_id) REFERENCES dbo.mold_machine_types(id) ON DELETE CASCADE;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_mold_parameter_targets_machine_type'
      AND object_id = OBJECT_ID(N'dbo.mold_parameter_targets')
)
BEGIN
    CREATE INDEX IX_mold_parameter_targets_machine_type
        ON dbo.mold_parameter_targets(machine_type_id);
END;
GO

-- ---------------------------------------------------------------------
-- 3. Re-key dbo.mold_extended_info: mold_id (PK) -> machine_type_id
--    mold_id was NOT NULL PRIMARY KEY; relaxed to NULL-able once the PK
--    is dropped below, since new rows are keyed only by machine_type_id.
-- ---------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.mold_extended_info') AND name = 'machine_type_id'
)
BEGIN
    ALTER TABLE dbo.mold_extended_info ADD machine_type_id BIGINT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_mold_extended_info_machine_type'
)
BEGIN
    ALTER TABLE dbo.mold_extended_info
        ADD CONSTRAINT FK_mold_extended_info_machine_type
            FOREIGN KEY (machine_type_id) REFERENCES dbo.mold_machine_types(id) ON DELETE CASCADE;
END;
GO

-- ---------------------------------------------------------------------
-- 4. Backfill: give every mold that already has data a default 机型
--    ("默认机型"), mark it main, and repoint existing rows at it.
-- ---------------------------------------------------------------------
INSERT INTO dbo.mold_machine_types (mold_id, machine_type, is_main)
SELECT DISTINCT m.id, N'默认机型', 1
FROM dbo.molds AS m
WHERE (
        EXISTS (SELECT 1 FROM dbo.mold_parameter_targets AS t WHERE t.mold_id = m.id AND t.machine_type_id IS NULL)
        OR EXISTS (SELECT 1 FROM dbo.mold_extended_info AS e WHERE e.mold_id = m.id AND e.machine_type_id IS NULL)
      )
  AND NOT EXISTS (SELECT 1 FROM dbo.mold_machine_types AS mt WHERE mt.mold_id = m.id);
GO

-- Every mold still has no machine type at all (e.g. brand-new molds with
-- no specs yet) also gets a default main machine type, so the frontend
-- always has at least one entry to show/select.
INSERT INTO dbo.mold_machine_types (mold_id, machine_type, is_main)
SELECT m.id, N'默认机型', 1
FROM dbo.molds AS m
WHERE NOT EXISTS (SELECT 1 FROM dbo.mold_machine_types AS mt WHERE mt.mold_id = m.id);
GO

UPDATE t
SET t.machine_type_id = mt.id
FROM dbo.mold_parameter_targets AS t
INNER JOIN dbo.mold_machine_types AS mt
    ON mt.mold_id = t.mold_id AND mt.is_main = 1
WHERE t.machine_type_id IS NULL;
GO

UPDATE e
SET e.machine_type_id = mt.id
FROM dbo.mold_extended_info AS e
INNER JOIN dbo.mold_machine_types AS mt
    ON mt.mold_id = e.mold_id AND mt.is_main = 1
WHERE e.machine_type_id IS NULL;
GO

-- ---------------------------------------------------------------------
-- 5. mold_extended_info's PK was mold_id alone (one row per mold) --
--    now it must be one row per (mold_id, machine_type_id). Drop the old
--    PK and use machine_type_id (already unique per row after backfill,
--    since each mold only had one row) as the new PK.
-- ---------------------------------------------------------------------
IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE type = 'PK' AND parent_object_id = OBJECT_ID(N'dbo.mold_extended_info')
      AND name != N'PK_mold_extended_info_machine_type'
)
BEGIN
    DECLARE @pk_name NVARCHAR(200);
    SELECT @pk_name = name FROM sys.key_constraints
    WHERE type = 'PK' AND parent_object_id = OBJECT_ID(N'dbo.mold_extended_info');
    EXEC('ALTER TABLE dbo.mold_extended_info DROP CONSTRAINT ' + @pk_name);
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.mold_extended_info') AND name = 'mold_id' AND is_nullable = 0
)
BEGIN
    ALTER TABLE dbo.mold_extended_info ALTER COLUMN mold_id BIGINT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_mold_extended_info_machine_type'
      AND object_id = OBJECT_ID(N'dbo.mold_extended_info')
)
BEGIN
    CREATE UNIQUE INDEX UX_mold_extended_info_machine_type
        ON dbo.mold_extended_info(machine_type_id)
        WHERE machine_type_id IS NOT NULL;
END;
GO

-- ---------------------------------------------------------------------
-- 6. Old mold_id columns on both tables are kept (not dropped) for
--    backward-compatible reads/rollback safety, but are no longer the
--    lookup key going forward -- backend code now filters/writes by
--    machine_type_id exclusively. Left as NULL-able, unindexed baggage.
-- ---------------------------------------------------------------------