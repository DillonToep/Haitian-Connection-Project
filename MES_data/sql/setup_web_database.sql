USE MES_MQTT;
GO

IF OBJECT_ID(N'dbo.app_users', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.app_users
    (
        id              INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        username        NVARCHAR(100) NOT NULL,
        password_hash   VARBINARY(32) NOT NULL,
        password_salt   VARBINARY(16) NOT NULL,
        role            NVARCHAR(30) NOT NULL DEFAULT N'operator',
        is_active       BIT NOT NULL DEFAULT 1,
        created_at      DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at      DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT UQ_app_users_username UNIQUE (username),
        CONSTRAINT CK_app_users_role
            CHECK (role IN (N'admin', N'operator', N'viewer'))
    );
END;
GO

IF OBJECT_ID(N'dbo.app_sessions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.app_sessions
    (
        token_hash      BINARY(32) NOT NULL PRIMARY KEY,
        user_id         INT NOT NULL,
        created_at      DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        expires_at      DATETIME2(3) NOT NULL,

        CONSTRAINT FK_app_sessions_user
            FOREIGN KEY (user_id)
            REFERENCES dbo.app_users(id)
            ON DELETE CASCADE
    );

    CREATE INDEX IX_app_sessions_expiry
        ON dbo.app_sessions(expires_at);
END;
GO

IF OBJECT_ID(N'dbo.molds', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.molds
    (
        id              BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        mold_code       NVARCHAR(100) NOT NULL,
        mold_name       NVARCHAR(200) NOT NULL,
        product_code    NVARCHAR(100) NULL,
        cavities        INT NOT NULL DEFAULT 1,
        remark          NVARCHAR(500) NULL,
        is_active       BIT NOT NULL DEFAULT 1,
        created_by      INT NULL,
        created_at      DATETIME2(3) NOT NULL DEFAULT SYSDATETIME(),
        updated_at      DATETIME2(3) NOT NULL DEFAULT SYSDATETIME(),

        CONSTRAINT UQ_molds_code UNIQUE (mold_code),
        CONSTRAINT CK_molds_cavities CHECK (cavities > 0),
        CONSTRAINT FK_molds_created_by
            FOREIGN KEY (created_by)
            REFERENCES dbo.app_users(id)
    );
END;
GO

IF OBJECT_ID(N'dbo.device_mold_assignments', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.device_mold_assignments
    (
        id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        device_id           NVARCHAR(100) NOT NULL,
        mold_id             BIGINT NOT NULL,
        mounted_at          DATETIME2(3) NOT NULL DEFAULT SYSDATETIME(),
        unmounted_at        DATETIME2(3) NULL,
        operator_user_id    INT NULL,
        remark              NVARCHAR(500) NULL,

        CONSTRAINT FK_device_mold_mold
            FOREIGN KEY (mold_id)
            REFERENCES dbo.molds(id),
        CONSTRAINT FK_device_mold_user
            FOREIGN KEY (operator_user_id)
            REFERENCES dbo.app_users(id),
        CONSTRAINT CK_device_mold_time
            CHECK (unmounted_at IS NULL OR unmounted_at >= mounted_at)
    );

    CREATE UNIQUE INDEX UX_device_mold_active_device
        ON dbo.device_mold_assignments(device_id)
        WHERE unmounted_at IS NULL;

    CREATE UNIQUE INDEX UX_device_mold_active_mold
        ON dbo.device_mold_assignments(mold_id)
        WHERE unmounted_at IS NULL;

    CREATE INDEX IX_device_mold_history
        ON dbo.device_mold_assignments(device_id, mounted_at DESC);
END;
GO