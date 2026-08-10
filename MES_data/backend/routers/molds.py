from contextlib import closing

import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from ..database import get_connection, row_to_dict
from ..schemas import MoldAssignmentRequest, MoldCreateRequest, MoldUpdateRequest
from ..security import require_editor, require_user


router = APIRouter(prefix="/api", tags=["molds"])


@router.get("/molds")
def get_molds(user: dict = Depends(require_user)):
    del user
    sql = """
        SELECT
            m.id, m.mold_code, m.mold_name, m.product_code,
            m.cavities, m.remark, m.is_active,
            a.device_id AS mounted_device_id, a.mounted_at
        FROM dbo.molds AS m
        LEFT JOIN dbo.device_mold_assignments AS a
            ON a.mold_id = m.id AND a.unmounted_at IS NULL
        ORDER BY m.is_active DESC, m.mold_code
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [row_to_dict(cursor, row) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/molds", status_code=201)
def create_mold(data: MoldCreateRequest, user: dict = Depends(require_user)):
    require_editor(user)
    sql = """
        INSERT INTO dbo.molds
            (mold_code, mold_name, product_code, cavities, remark, created_by)
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?)
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold_id = cursor.execute(
                sql,
                data.mold_code.strip(),
                data.mold_name.strip(),
                data.product_code.strip() if data.product_code else None,
                data.cavities,
                data.remark.strip() if data.remark else None,
                user["id"],
            ).fetchone()[0]
            connection.commit()
            return {"status": "ok", "id": mold_id}
    except pyodbc.IntegrityError as error:
        raise HTTPException(status_code=409, detail="模具编号已经存在") from error
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.put("/molds/{mold_id}")
def update_mold(
    mold_id: int,
    data: MoldUpdateRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    sql = """
        UPDATE dbo.molds
        SET mold_code = ?, mold_name = ?, product_code = ?, cavities = ?,
            remark = ?, is_active = ?, updated_at = SYSDATETIME()
        WHERE id = ?
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                sql,
                data.mold_code.strip(),
                data.mold_name.strip(),
                data.product_code.strip() if data.product_code else None,
                data.cavities,
                data.remark.strip() if data.remark else None,
                data.is_active,
                mold_id,
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="模具不存在")
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.IntegrityError as error:
        raise HTTPException(status_code=409, detail="模具编号已经存在") from error
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/devices/{device_id}/mold")
def mount_mold(
    device_id: str,
    data: MoldAssignmentRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute(
                "SELECT id FROM dbo.molds WHERE id = ? AND is_active = 1",
                data.mold_id,
            ).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在或已停用")

            occupied = cursor.execute(
                """
                SELECT device_id FROM dbo.device_mold_assignments
                WHERE mold_id = ? AND unmounted_at IS NULL AND device_id <> ?
                """,
                data.mold_id,
                device_id,
            ).fetchone()
            if occupied:
                raise HTTPException(
                    status_code=409,
                    detail=f"该模具当前安装在设备 {occupied.device_id}",
                )

            current = cursor.execute(
                """
                SELECT mold_id FROM dbo.device_mold_assignments
                WHERE device_id = ? AND unmounted_at IS NULL
                """,
                device_id,
            ).fetchone()
            if current and current.mold_id == data.mold_id:
                raise HTTPException(status_code=409, detail="该设备已经安装此模具")

            cursor.execute(
                """
                UPDATE dbo.device_mold_assignments SET unmounted_at = SYSDATETIME()
                WHERE device_id = ? AND unmounted_at IS NULL
                """,
                device_id,
            )
            cursor.execute(
                """
                INSERT INTO dbo.device_mold_assignments
                    (device_id, mold_id, operator_user_id, remark)
                VALUES (?, ?, ?, ?)
                """,
                device_id,
                data.mold_id,
                user["id"],
                data.remark.strip() if data.remark else None,
            )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.IntegrityError as error:
        raise HTTPException(status_code=409, detail="装模状态发生冲突，请刷新后重试") from error
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.delete("/devices/{device_id}/mold")
def unmount_mold(device_id: str, user: dict = Depends(require_user)):
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.device_mold_assignments SET unmounted_at = SYSDATETIME()
                WHERE device_id = ? AND unmounted_at IS NULL
                """,
                device_id,
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="该设备当前没有安装模具")
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/devices/{device_id}/mold-history")
def get_mold_history(device_id: str, user: dict = Depends(require_user)):
    del user
    sql = """
        SELECT TOP 100
            a.id, a.device_id, a.mounted_at, a.unmounted_at, a.remark,
            m.id AS mold_id, m.mold_code, m.mold_name, m.product_code,
            u.username AS operator_username
        FROM dbo.device_mold_assignments AS a
        INNER JOIN dbo.molds AS m ON m.id = a.mold_id
        LEFT JOIN dbo.app_users AS u ON u.id = a.operator_user_id
        WHERE a.device_id = ?
        ORDER BY a.mounted_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            return [row_to_dict(cursor, row) for row in cursor.fetchall()]
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
