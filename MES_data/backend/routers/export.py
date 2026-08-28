from contextlib import closing
import json

import pyodbc
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..database import get_connection
from ..export_xlsx import build_trial_parameter_workbook
from ..security import require_user


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
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )