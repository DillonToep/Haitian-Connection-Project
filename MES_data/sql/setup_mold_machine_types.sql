-- Adds a Machine Type link to a device's active mold assignment:
--   Physical Machine -> Mold -> Machine Type -> Specifications
--
-- Previously, tolerance/production notifications for a device resolved
-- specifications via the mold's is_main machine type
-- (dbo.mold_machine_types.is_main -- see setup_mold_machine_types.sql).
-- That meant every device running the same mold shared one machine type,
-- and switching "main" affected every device with that mold mounted.
--
-- This migration adds dbo.device_mold_assignments.machine_type_id, so
-- each physical machine's *own* active assignment says exactly which of
-- the mold's machine types it should use. is_main is left completely
-- intact (still used to seed new machine types' defaults, still shown as
-- "主要机型" in 模具管理), it just no longer drives notification lookups --
-- see the rewritten _fetch_mold_targets in mqtt_monitor.py.
--
-- Nothing is copied: device_mold_assignments.machine_type_id is only a
-- pointer to the existing dbo.mold_parameter_targets /
-- dbo.mold_extended_info rows already keyed by machine_type_id.

USE MES_MQTT;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.device_mold_assignments') AND name = 'machine_type_id'
)
BEGIN
    ALTER TABLE dbo.device_mold_assignments ADD machine_type_id BIGINT NULL;
END;
GO

-- ON DELETE SET NULL (not CASCADE, not a blocking FK): deleting a machine
-- type that's still referenced by a *historical* (already-unmounted)
-- assignment row should not be blocked by that old record, and deleting
-- a mold (which cascades to its machine types) should not fail because
-- of an old device_mold_assignments row pointing at one of them. Deleting
-- a machine type that's still *actively* assigned to a device is blocked
-- separately, at the application layer (see delete_mold_machine_type in
-- molds.py), which gives a clear "in use" error instead of a raw FK
-- failure.
IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_device_mold_assignments_machine_type'
)
BEGIN
    ALTER TABLE dbo.device_mold_assignments
        ADD CONSTRAINT FK_device_mold_assignments_machine_type
            FOREIGN KEY (machine_type_id)
            REFERENCES dbo.mold_machine_types(id)
            ON DELETE SET NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_device_mold_assignments_machine_type'
      AND object_id = OBJECT_ID(N'dbo.device_mold_assignments')
)
BEGIN
    CREATE INDEX IX_device_mold_assignments_machine_type
        ON dbo.device_mold_assignments(machine_type_id);
END;
GO

-- Backfill: every device that already has a mold mounted gets that
-- mold's current is_main machine type as its starting machine_type_id,
-- so nothing silently stops getting notifications the moment this
-- migration runs. From here on, is_main no longer matters for this --
-- changing a device's machine type is done explicitly via
-- POST /api/devices/{device_id}/mold or
-- PUT /api/devices/{device_id}/machine-type.
UPDATE a
SET a.machine_type_id = mt.id
FROM dbo.device_mold_assignments AS a
INNER JOIN dbo.mold_machine_types AS mt
    ON mt.mold_id = a.mold_id AND mt.is_main = 1
WHERE a.machine_type_id IS NULL;
GO