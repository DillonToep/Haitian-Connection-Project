USE MES_MQTT;
GO

-- Up to 4 images per mold project, one flagged as the "face" (card) image.
IF OBJECT_ID(N'dbo.mold_images', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_images
    (
        id          BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        mold_id     BIGINT NOT NULL,
        file_path   NVARCHAR(400) NOT NULL,
        is_face     BIT NOT NULL DEFAULT 0,
        sort_order  INT NOT NULL DEFAULT 0,
        created_at  DATETIME2(3) NOT NULL DEFAULT SYSDATETIME(),

        CONSTRAINT FK_mold_images_mold
            FOREIGN KEY (mold_id) REFERENCES dbo.molds(id) ON DELETE CASCADE
    );

    CREATE INDEX IX_mold_images_mold ON dbo.mold_images(mold_id);

    -- Only one face image per mold.
    CREATE UNIQUE INDEX UX_mold_images_face
        ON dbo.mold_images(mold_id)
        WHERE is_face = 1;
END;
GO

IF OBJECT_ID(N'dbo.mold_cavity_temperatures', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_cavity_temperatures
    (
        id              BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        mold_id         BIGINT NOT NULL,
        cavity_label    NVARCHAR(20) NOT NULL,      -- e.g. IN1, OUT1
        temperature_c   DECIMAL(6,2) NULL,
        sort_order      INT NOT NULL DEFAULT 0,

        CONSTRAINT FK_mold_cavity_temp_mold
            FOREIGN KEY (mold_id) REFERENCES dbo.molds(id) ON DELETE CASCADE,
        CONSTRAINT UQ_mold_cavity_temp UNIQUE (mold_id, cavity_label)
    );

    CREATE INDEX IX_mold_cavity_temp_mold
        ON dbo.mold_cavity_temperatures(mold_id, sort_order);
END;
GO