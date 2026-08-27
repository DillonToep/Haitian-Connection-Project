USE MES_MQTT;
GO

-- Old constraint assumed every row was mold-scoped (mold_id, parameter_id).
-- Machine-type-scoped rows use mold_id = NULL + machine_type_id instead,
-- and SQL Server unique constraints treat NULLs as duplicates of each
-- other, so a second machine type reusing the same parameter_id collides
-- on (NULL, parameter_id) even though it's a different machine type.

IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = N'UQ_mold_parameter_targets'
      AND parent_object_id = OBJECT_ID(N'dbo.mold_parameter_targets')
)
BEGIN
    ALTER TABLE dbo.mold_parameter_targets DROP CONSTRAINT UQ_mold_parameter_targets;
END;
GO

-- Fallback in case it was created as a plain unique index rather than
-- a named constraint.
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_mold_parameter_targets'
      AND object_id = OBJECT_ID(N'dbo.mold_parameter_targets')
)
BEGIN
    DROP INDEX UQ_mold_parameter_targets ON dbo.mold_parameter_targets;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_mold_parameter_targets_mold'
      AND object_id = OBJECT_ID(N'dbo.mold_parameter_targets')
)
BEGIN
    CREATE UNIQUE INDEX UX_mold_parameter_targets_mold
        ON dbo.mold_parameter_targets(mold_id, parameter_id)
        WHERE mold_id IS NOT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_mold_parameter_targets_machine_type'
      AND object_id = OBJECT_ID(N'dbo.mold_parameter_targets')
)
BEGIN
    CREATE UNIQUE INDEX UX_mold_parameter_targets_machine_type
        ON dbo.mold_parameter_targets(machine_type_id, parameter_id)
        WHERE machine_type_id IS NOT NULL;
END;
GO