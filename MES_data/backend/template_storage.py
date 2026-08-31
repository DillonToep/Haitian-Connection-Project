"""Persistence for user-uploaded 试模成型参数表 templates.

Per the "Excel Import, Web Editing, and Export" feature: once a user
uploads an Excel workbook for a Mold + Machine Type, that exact workbook
(bytes, formatting, images, merges, column widths, etc.) becomes the
template used for all future exports of that Machine Type -- exports
write updated values into a copy of THIS file rather than regenerating a
fresh sheet from backend/export_xlsx.py's built-in static template
(see overlay_values_onto_template there).

One active template per machine_type_id (dbo.mold_trial_sheet_templates,
see sql/setup_trial_templates.sql). Uploading again replaces the stored
file -- there is intentionally no history/versioning, mirroring how mold
images are replaced on edit rather than accumulated.
"""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import uuid

from .config import TRIAL_TEMPLATE_DIR
from .database import get_connection


@dataclass
class TrialTemplateRecord:
    machine_type_id: int
    original_filename: str
    file_path: str
    uploaded_at: object


def _extension_for(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".xlsm"):
        return ".xlsm"
    return ".xlsx"  # default/fallback covers .xlsx and anything unrecognized


def save_trial_template(machine_type_id: int, filename: str, content: bytes, user_id: int) -> None:
    """Persists the uploaded workbook to disk and records/replaces its
    metadata row. Any previously stored file for this machine type is
    deleted from disk afterwards, so exactly one template file exists per
    machine type at a time and the uploads directory doesn't grow
    unbounded across repeated re-uploads."""
    ext = _extension_for(filename)
    dest = TRIAL_TEMPLATE_DIR / f"{machine_type_id}_{uuid.uuid4().hex}{ext}"

    with closing(get_connection()) as connection:
        cursor = connection.cursor()
        existing = cursor.execute(
            "SELECT file_path FROM dbo.mold_trial_sheet_templates WHERE machine_type_id = ?",
            machine_type_id,
        ).fetchone()

        dest.write_bytes(content)

        cursor.execute(
            """
            MERGE dbo.mold_trial_sheet_templates AS target
            USING (SELECT ? AS machine_type_id) AS src
            ON target.machine_type_id = src.machine_type_id
            WHEN MATCHED THEN
                UPDATE SET original_filename = ?, file_path = ?,
                           uploaded_at = SYSUTCDATETIME(), uploaded_by = ?
            WHEN NOT MATCHED THEN
                INSERT (machine_type_id, original_filename, file_path, uploaded_by)
                VALUES (src.machine_type_id, ?, ?, ?);
            """,
            machine_type_id,
            filename, str(dest), user_id,
            filename, str(dest), user_id,
        )
        connection.commit()

    if existing and existing.file_path and existing.file_path != str(dest):
        try:
            Path(existing.file_path).unlink(missing_ok=True)
        except OSError:
            pass  # stale file left behind is harmless; nothing references it anymore


def get_trial_template(machine_type_id: int) -> TrialTemplateRecord | None:
    with closing(get_connection()) as connection:
        cursor = connection.cursor()
        row = cursor.execute(
            "SELECT machine_type_id, original_filename, file_path, uploaded_at "
            "FROM dbo.mold_trial_sheet_templates WHERE machine_type_id = ?",
            machine_type_id,
        ).fetchone()
    if row is None:
        return None
    return TrialTemplateRecord(
        machine_type_id=row.machine_type_id,
        original_filename=row.original_filename,
        file_path=row.file_path,
        uploaded_at=row.uploaded_at,
    )


def delete_trial_template(machine_type_id: int) -> bool:
    """Removes the stored template (DB row + file on disk). After this,
    exporting that machine type falls back to the generated static
    template again. Returns False if there was nothing to delete."""
    with closing(get_connection()) as connection:
        cursor = connection.cursor()
        row = cursor.execute(
            "SELECT file_path FROM dbo.mold_trial_sheet_templates WHERE machine_type_id = ?",
            machine_type_id,
        ).fetchone()
        if row is None:
            return False
        cursor.execute(
            "DELETE FROM dbo.mold_trial_sheet_templates WHERE machine_type_id = ?",
            machine_type_id,
        )
        connection.commit()

    try:
        Path(row.file_path).unlink(missing_ok=True)
    except OSError:
        pass
    return True