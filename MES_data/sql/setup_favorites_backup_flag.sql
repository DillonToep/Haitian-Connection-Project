USE MES_MQTT;
GO

-- Distinguishes an auto-generated backup (created when applying a favorite
-- overwrites a schematic that already had values -- see
-- apply_favorite_to_schematic in favorites.py) from a favorite the user
-- explicitly named and saved (create_favorite_from_changelog). Previously
-- these were only distinguishable by matching the "自动备份 " name prefix,
-- which is fragile (a user could name a favorite that way too) and not
-- something SQL should sort on. GET .../favorites now orders named
-- favorites first (newest first), with backups pushed to the bottom
-- (also newest first) -- see list_favorites in favorites.py.
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.mold_favorite_snapshots') AND name = 'is_backup'
)
BEGIN
    ALTER TABLE dbo.mold_favorite_snapshots ADD is_backup BIT NOT NULL DEFAULT 0;
END;
GO

-- Backfill: anything that already matches the auto-backup naming
-- convention is almost certainly one -- flip it so existing data sorts
-- correctly right away instead of only new rows going forward.
UPDATE dbo.mold_favorite_snapshots
SET is_backup = 1
WHERE name LIKE N'自动备份 %' AND is_backup = 0;
GO

-- Fast lookup for the ordering used by GET .../favorites.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_mold_favorite_snapshots_backup_order'
      AND object_id = OBJECT_ID(N'dbo.mold_favorite_snapshots')
)
BEGIN
    CREATE INDEX IX_mold_favorite_snapshots_backup_order
        ON dbo.mold_favorite_snapshots(machine_type_id, is_backup, updated_at DESC);
END;
GO