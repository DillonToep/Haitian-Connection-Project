from contextlib import closing
import json
from pathlib import Path
from urllib.parse import quote

import pyodbc
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..config import DEFAULT_TRIAL_TEMPLATE_PATH
from ..database import get_connection
from ..export_xlsx import build_trial_parameter_workbook, overlay_values_onto_template
from ..import_xlsx import parse_trial_parameter_workbook
from ..parameter_labels import EXCLUDED_FROM_TARGETS, PARAMETER_LABELS
from ..security import require_editor, require_user
from ..template_storage import delete_trial_template, get_trial_template, save_trial_template
from ..xls_convert import convert_xls_to_xlsx_bytes


router = APIRouter(prefix="/api", tags=["export"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSM_MEDIA_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.12"


def _get_machine_type_or_404(cursor, mold_id: int, machine_type_id: int):
    row = cursor.execute(
        "SELECT id FROM dbo.mold_machine_types WHERE id = ? AND mold_id = ?",
        machine_type_id, mold_id,
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="机型不存在")
    return row


@router.get("/molds/{mold_id}/machine-types/{machine_type_id}/export")
def export_trial_parameter_sheet(
    mold_id: int,
    machine_type_id: int,
    user: dict = Depends(require_user),
):
    """Generates the 试模成型参数表 (.xlsx/.xlsm) for one Mold + Machine
    Type.

    If a workbook was previously uploaded for this machine type (see
    POST .../import below), THAT exact file is used as the base -- a copy
    of it is opened, only the mapped cells are overwritten with current
    MES values (blank if a mapped field currently has no value), and
    everything else (formatting, merges, images, formulas, layout) is
    preserved untouched. This is the "upload -> edit in app -> export
    back into the same file" workflow. A .xls upload is converted to
    .xlsx at import time (see convert_xls_to_xlsx_bytes) so it goes
    through this exact same path -- see import_trial_parameter_sheet.

    If nothing has ever been uploaded for this machine type, this falls
    back to a global default template (backend/assets/
    default_trial_template.xlsx, see config.DEFAULT_TRIAL_TEMPLATE_PATH)
    -- a real, correctly-formatted blank copy of the company's sheet --
    written into via the SAME overlay_values_onto_template() path a real
    upload uses, so export looks identical whether or not anyone has
    ever uploaded a per-machine-type file. Only if that default file is
    somehow missing from disk does this drop back to the old behavior:
    a fresh sheet generated from the built-in static template embedded
    in backend/export_xlsx.py.
    """
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()

            mold_row = cursor.execute(
                "SELECT mold_code, mold_name, cavities FROM dbo.molds WHERE id = ?",
                mold_id,
            ).fetchone()
            if mold_row is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            _get_machine_type_or_404(cursor, mold_id, machine_type_id)

            cursor.execute(
                "SELECT parameter_id, target_value FROM dbo.mold_parameter_targets "
                "WHERE machine_type_id = ?",
                machine_type_id,
            )
            parameters_by_tag = {
                row.parameter_id: {"target_value": row.target_value}
                for row in cursor.fetchall()
            }

            extended_row = cursor.execute(
                "SELECT info_json FROM dbo.mold_extended_info WHERE machine_type_id = ?",
                machine_type_id,
            ).fetchone()
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    extended_fields = json.loads(extended_row.info_json) if extended_row and extended_row.info_json else {}
    mold = {
        "mold_code": mold_row.mold_code,
        "mold_name": mold_row.mold_name,
        "cavities": mold_row.cavities,
    }

    template = get_trial_template(machine_type_id)
    original_bytes = None
    if template is not None:
        try:
            original_bytes = Path(template.file_path).read_bytes()
        except OSError:
            template = None  # file missing on disk -- fall back below

    if template is not None and original_bytes is not None:
        is_macro = template.original_filename.lower().endswith(".xlsm")
        buffer = overlay_values_onto_template(original_bytes, is_macro, mold, parameters_by_tag, extended_fields)
        filename = template.original_filename
        media_type = XLSM_MEDIA_TYPE if is_macro else XLSX_MEDIA_TYPE
    else:
        # No per-machine-type upload on file -- use the global default
        # blank template (a real file, correct formatting) instead of
        # regenerating a sheet from the embedded static _TEMPLATE, so
        # export behaves the same as the "upload -> export" path even
        # when nobody has ever uploaded anything for this machine type.
        try:
            default_bytes = DEFAULT_TRIAL_TEMPLATE_PATH.read_bytes()
            buffer = overlay_values_onto_template(default_bytes, False, mold, parameters_by_tag, extended_fields)
            filename = f"{mold['mold_code']}_试模成型参数表.xlsx"
            media_type = XLSX_MEDIA_TYPE
        except OSError:
            # Default template missing from disk entirely -- last-resort
            # fallback to the old generated-from-scratch sheet, so export
            # never hard-fails outright.
            buffer = build_trial_parameter_workbook(mold, parameters_by_tag, extended_fields)
            filename = f"{mold['mold_code']}_试模成型参数表.xlsx"
            media_type = XLSX_MEDIA_TYPE

    encoded_filename = quote(filename)  # percent-encode: headers must be latin-1
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.get("/molds/{mold_id}/machine-types/{machine_type_id}/template")
def get_template_status(
    mold_id: int,
    machine_type_id: int,
    user: dict = Depends(require_user),
):
    """Tells the frontend whether exports for this machine type currently
    write back into a previously uploaded workbook, or fall back to the
    generated static template."""
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            _get_machine_type_or_404(cursor, mold_id, machine_type_id)
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    template = get_trial_template(machine_type_id)
    if template is None:
        return {"has_template": False}
    return {
        "has_template": True,
        "original_filename": template.original_filename,
        "uploaded_at": template.uploaded_at,
    }


@router.delete("/molds/{mold_id}/machine-types/{machine_type_id}/template")
def remove_template(
    mold_id: int,
    machine_type_id: int,
    user: dict = Depends(require_user),
):
    """Forgets the uploaded workbook for this machine type. After this,
    GET .../export reverts to the global default template (see
    DEFAULT_TRIAL_TEMPLATE_PATH). Does not touch any already-imported MES
    values (mold_parameter_targets / mold_extended_info) -- those stay
    as-is."""
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            _get_machine_type_or_404(cursor, mold_id, machine_type_id)
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    if not delete_trial_template(machine_type_id):
        raise HTTPException(status_code=404, detail="尚未上传过原始文件")
    return {"status": "ok"}


@router.post("/molds/{mold_id}/machine-types/{machine_type_id}/import")
async def import_trial_parameter_sheet(
    mold_id: int,
    machine_type_id: int,
    user: dict = Depends(require_user),
    file: UploadFile = File(...),
):
    """Reads an uploaded 试模成型参数表 (.xlsx/.xlsm/.xls/.csv) and:

      1. Writes whatever mapped values it finds onto this Mold + Machine
         Type's 高级工艺参数 (dbo.mold_parameter_targets) and extended info
         (dbo.mold_extended_info) -- same as before.
      2. Stores the uploaded workbook as this machine type's export
         template (see backend/template_storage.py). From now on, GET
         .../export writes updated values back into a copy of THIS
         exact file -- preserving its formatting, merges, images, and
         layout -- instead of the global default template.

         .xlsx/.xlsm uploads are stored as-is. A .xls upload (legacy
         Excel 97-2003 / BIFF format) is first converted to an
         equivalent .xlsx (see xls_convert.convert_xls_to_xlsx_bytes),
         since the overlay step on export is openpyxl-based and cannot
         open .xls directly. Without this conversion, a .xls upload was
         silently never saved as a template at all -- values were still
         parsed and saved to the database correctly, but every export
         fell back to the generic default template instead of the
         uploaded sheet's own layout/branding. .csv uploads still can't
         be used as an export template (no layout/formatting to
         preserve) and continue to only feed the value import in step 1.

         If .xls conversion fails (e.g. a corrupted workbook, or one in
         an even older format xlrd can't read), the import still
         succeeds -- the values are saved -- but no template is stored,
         matching the pre-existing .csv behavior, and
         `template_saved: false` is returned so the frontend can tell
         the user their layout wasn't preserved.

      3. 模具编号/产品名称/模穴数 read from the sheet header are returned to
         the caller as `header_read_only` for review, but are NOT applied
         automatically -- see PUT /api/molds/{mold_id} for that instead.

    Import is additive/overlay, never destructive to the DB values:
      - A blank cell means "leave the existing saved value alone", not
        "clear it" -- only tags/fields the sheet actually has a value for
        are touched.
      - An existing tag's tolerance_mode/tolerance_percent/tolerance_flat
        are left completely untouched; only target_value is overwritten.
    """
    require_editor(user)

    filename_lower = (file.filename or "").lower()
    if not filename_lower.endswith((".xlsx", ".xlsm", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx / .xls / .csv 文件")

    content = await file.read()
    try:
        parsed = parse_trial_parameter_workbook(content, file.filename)
    except Exception as error:  # noqa: BLE001 -- surface any parse failure as a clean 400
        raise HTTPException(status_code=400, detail=f"文件解析失败：{error}") from error

    valid_tags = set(PARAMETER_LABELS.keys()) - EXCLUDED_FROM_TARGETS
    incoming_parameters = {
        tag: value for tag, value in parsed["parameters"].items() if tag in valid_tags
    }

    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()

            machine_type_row = cursor.execute(
                "SELECT id FROM dbo.mold_machine_types WHERE id = ? AND mold_id = ?",
                machine_type_id, mold_id,
            ).fetchone()
            if machine_type_row is None:
                raise HTTPException(status_code=404, detail="机型不存在")

            existing_tags = {
                row.parameter_id
                for row in cursor.execute(
                    "SELECT parameter_id FROM dbo.mold_parameter_targets WHERE machine_type_id = ?",
                    machine_type_id,
                ).fetchall()
            }

            for tag, value in incoming_parameters.items():
                if tag in existing_tags:
                    cursor.execute(
                        """
                        UPDATE dbo.mold_parameter_targets
                        SET target_value = ?
                        WHERE machine_type_id = ? AND parameter_id = ?
                        """,
                        value, machine_type_id, tag,
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO dbo.mold_parameter_targets
                            (mold_id, machine_type_id, parameter_id, target_value, tolerance_mode)
                        VALUES (NULL, ?, ?, ?, N'percent')
                        """,
                        machine_type_id, tag, value,
                    )

            extended_row = cursor.execute(
                "SELECT info_json FROM dbo.mold_extended_info WHERE machine_type_id = ?",
                machine_type_id,
            ).fetchone()
            current_extended = (
                json.loads(extended_row.info_json) if extended_row and extended_row.info_json else {}
            )
            current_extended.update(parsed["extended"])
            extended_payload = json.dumps(current_extended, ensure_ascii=False)

            cursor.execute(
                """
                MERGE dbo.mold_extended_info AS target
                USING (SELECT ? AS machine_type_id) AS src
                ON target.machine_type_id = src.machine_type_id
                WHEN MATCHED THEN
                    UPDATE SET info_json = ?, updated_at = SYSUTCDATETIME(), updated_by = ?
                WHEN NOT MATCHED THEN
                    INSERT (mold_id, machine_type_id, info_json, updated_by)
                    VALUES (NULL, src.machine_type_id, ?, ?);
                """,
                machine_type_id, extended_payload, user["id"], extended_payload, user["id"],
            )

            connection.commit()
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    # ---- persist the uploaded file as this machine type's export template ----
    # .xlsx/.xlsm are stored verbatim. .xls is converted to .xlsx first,
    # since overlay_values_onto_template (used by GET .../export) is
    # openpyxl-based and cannot open .xls -- without this conversion a
    # .xls upload was silently never saved as a template at all, and
    # every subsequent export fell back to the global default sheet
    # instead of the uploaded file's own layout. .csv has no
    # layout/formatting worth preserving and is never saved as a template.
    template_saved = False
    conversion_failed = False
    if filename_lower.endswith((".xlsx", ".xlsm")):
        save_trial_template(machine_type_id, file.filename, content, user["id"])
        template_saved = True
    elif filename_lower.endswith(".xls"):
        try:
            converted_bytes = convert_xls_to_xlsx_bytes(content)
        except Exception:  # noqa: BLE001 -- any conversion failure just means "no template"
            conversion_failed = True
        else:
            stem = file.filename.rsplit(".", 1)[0] if file.filename and "." in file.filename else (file.filename or "template")
            save_trial_template(machine_type_id, f"{stem}.xlsx", converted_bytes, user["id"])
            template_saved = True

    return {
        "status": "ok",
        "parameters_imported": len(incoming_parameters),
        "extended_fields_imported": len(parsed["extended"]),
        "header_read_only": parsed["header"],
        "template_saved": template_saved,
        "template_conversion_failed": conversion_failed,
    }