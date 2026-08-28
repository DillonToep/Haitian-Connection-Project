USE MES_MQTT;
GO

-- A "favorite" is a full snapshot of every 工艺参数 tag reported by a
-- device at one specific moment (the raw_message_id behind a 变更记录
-- row), saved against a Mold + Machine Type (dbo.mold_machine_types.id)
-- so it lives alongside that machine type's other specifications.
--
-- parameters_json stores the same decorated array shape GET
-- /api/tech/{device_id} returns (parameter_id/label/category/value), so
-- the saved snapshot can be rendered with the exact same
-- PARAMETER_GRID_BLOCKS-driven tables the live 工艺参数 tab uses, without
-- needing the source mqtt_messages row to still exist.
--
-- Uniqueness is (machine_type_id, name): saving again under the same
-- name for the same machine type is an explicit overwrite, not a
-- duplicate -- see favorites.py's overwrite flag.
IF OBJECT_ID(N'dbo.mold_favorite_snapshots', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_favorite_snapshots
    (
        id                      BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        machine_type_id         BIGINT NOT NULL,
        name                    NVARCHAR(200) NOT NULL,
        device_id               NVARCHAR(100) NOT NULL,
        source_raw_message_id   BIGINT NULL,
        source_changelog_id     BIGINT NULL,
        captured_data_time      DATETIME2(3) NULL,
        parameters_json         NVARCHAR(MAX) NOT NULL,
        created_at              DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        created_by              INT NULL,
        updated_at              DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_by              INT NULL,

        CONSTRAINT FK_mold_favorite_snapshots_machine_type
            FOREIGN KEY (machine_type_id) REFERENCES dbo.mold_machine_types(id) ON DELETE CASCADE,
        CONSTRAINT FK_mold_favorite_snapshots_raw_message
            FOREIGN KEY (source_raw_message_id) REFERENCES dbo.mqtt_messages(id),
        CONSTRAINT FK_mold_favorite_snapshots_changelog
            FOREIGN KEY (source_changelog_id) REFERENCES dbo.tech_parameter_changelog(id),
        CONSTRAINT FK_mold_favorite_snapshots_created_by
            FOREIGN KEY (created_by) REFERENCES dbo.app_users(id),
        CONSTRAINT FK_mold_favorite_snapshots_updated_by
            FOREIGN KEY (updated_by) REFERENCES dbo.app_users(id)
    );

    CREATE UNIQUE INDEX UX_mold_favorite_snapshots_name
        ON dbo.mold_favorite_snapshots(machine_type_id, name);

    CREATE INDEX IX_mold_favorite_snapshots_machine_type
        ON dbo.mold_favorite_snapshots(machine_type_id, updated_at DESC);
END;
GO