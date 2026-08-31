-- Stores the original uploaded 试模成型参数表 workbook per Machine Type,
-- so exports can write values into a copy of THAT exact file instead of
-- regenerating a sheet from backend/export_xlsx.py's built-in static
-- template. One row = one machine type's "active" template; re-uploading
-- replaces it (see backend/template_storage.py -- no history is kept,
-- same convention as replacing a mold image).

USE MES_MQTT;
GO

IF OBJECT_ID(N'dbo.mold_trial_sheet_templates', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mold_trial_sheet_templates
    (
        machine_type_id     BIGINT NOT NULL PRIMARY KEY,
        original_filename   NVARCHAR(255) NOT NULL,
        file_path           NVARCHAR(400) NOT NULL,
        uploaded_at         DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        uploaded_by         INT NULL,

        CONSTRAINT FK_mold_trial_sheet_templates_machine_type
            FOREIGN KEY (machine_type_id)
            REFERENCES dbo.mold_machine_types(id)
            ON DELETE CASCADE,
        CONSTRAINT FK_mold_trial_sheet_templates_uploaded_by
            FOREIGN KEY (uploaded_by) REFERENCES dbo.app_users(id)
    );
END;
GO