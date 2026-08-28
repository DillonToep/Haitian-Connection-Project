from contextlib import closing
import json
from urllib.parse import quote

import pyodbc
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..database import get_connection
from ..export_xlsx import build_trial_parameter_workbook
from ..import_xlsx import parse_trial_parameter_workbook
from ..parameter_labels import EXCLUDED_FROM_TARGETS, PARAMETER_LABELS
from ..security import require_editor, require_user


router = APIRouter(prefix="/api", tags=["export"])


@router.get("/molds/{mold_id}/machine-types/{machine_type_id}/export")
def export_trial_parameter_sheet(
    mold_id: int,
    machine_type_id: int,
    user: dict = Depends(require_user),
):
    """Generates the company's 试模成型参数表 (.xlsx) for one Mold +
    Machine Type, filling in only the cells that have a confident match
    to data already stored in the MES (see export_xlsx.py for the exact
    field mapping). Everything else -- 试模员/试模日期/审核, the 试模结果
    defect checklist, etc. -- is left blank for the operator to fill in
    by hand during the actual trial run."""
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

            machine_type_row = cursor.execute(
                "SELECT id FROM dbo.mold_machine_types WHERE id = ? AND mold_id = ?",
                machine_type_id, mold_id,
            ).fetchone()
            if machine_type_row is None:
                raise HTTPException(status_code=404, detail="机型不存在")

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

    buffer = build_trial_parameter_workbook(mold, parameters_by_tag, extended_fields)
    filename = f"{mold['mold_code']}_试模成型参数表.xlsx"
    encoded_filename = quote(filename)  # percent-encode: headers must be latin-1
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/molds/{mold_id}/machine-types/{machine_type_id}/import")
async def import_trial_parameter_sheet(
    mold_id: int,
    machine_type_id: int,
    user: dict = Depends(require_user),
    file: UploadFile = File(...),
):
    """Reads a filled-in 试模成型参数表 (.xlsx) -- typically one previously
    exported by the endpoint above, then edited by hand during a trial
    run -- and writes whatever values it finds back onto this Mold +
    Machine Type's 高级工艺参数 (dbo.mold_parameter_targets) and extended
    info (dbo.mold_extended_info).

    Import is additive/overlay, never destructive:
      - A blank cell means "leave the existing saved value alone", not
        "clear it" -- only tags/fields the sheet actually has a value for
        are touched.
      - An existing tag's tolerance_mode/tolerance_percent/tolerance_flat
        are left completely untouched; only target_value is overwritten
        (mirrors how applying a favorite works in favorites.py).
      - 模具编号/产品名称/模穴数 read from the sheet header are returned to
        the caller as `header_read_only` for review, but are NOT applied
        automatically -- changing those has wider effects (unique
        mold_code constraint, cavity-temperature row count, etc.) that
        deserve an explicit edit through PUT /api/molds/{mold_id}
        instead of an implicit side effect of an xlsx import.
    """
    require_editor(user)

    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 文件")

    content = await file.read()
    try:
        parsed = parse_trial_parameter_workbook(content)
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

    return {
        "status": "ok",
        "parameters_imported": len(incoming_parameters),
        "extended_fields_imported": len(parsed["extended"]),
        "header_read_only": parsed["header"],
    }