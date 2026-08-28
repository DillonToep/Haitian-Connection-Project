from contextlib import closing
import json

import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from ..database import get_connection, row_to_dict
from ..parameter_labels import PARAMETER_LABELS, categorize_tag
from ..schemas import FavoriteCreateRequest
from ..security import require_editor, require_user


router = APIRouter(prefix="/api", tags=["favorites"])


def _build_parameters_snapshot(cursor, device_id: str, raw_message_id: int) -> list[dict]:
    """Same decorated shape GET /api/tech/{device_id} returns, but pinned
    to one specific raw_message_id instead of "latest" -- this is what
    lets a favorite freeze the exact reading behind a 变更记录 row rather
    than whatever the device is reporting right now."""
    cursor.execute(
        """
        SELECT parameter_id, parameter_value_text, parameter_value
        FROM dbo.vw_machine_tech
        WHERE device_id = ? AND raw_message_id = ?
        ORDER BY parameter_id
        """,
        device_id,
        raw_message_id,
    )
    rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="该时间点没有找到工艺参数数据")

    parameters = []
    for row in rows:
        tag_id = row.parameter_id
        value = row.parameter_value if row.parameter_value is not None else row.parameter_value_text
        meta = PARAMETER_LABELS.get(tag_id)
        if meta is None:
            parameters.append(
                {"parameter_id": tag_id, "label": tag_id, "category": "未知参数", "value": value}
            )
            continue
        if not meta["use"]:
            continue
        parameters.append(
            {
                "parameter_id": tag_id,
                "label": meta["label"],
                "category": categorize_tag(tag_id, meta["label"]),
                "value": value,
            }
        )
    return parameters


def _get_machine_type_or_404(cursor, machine_type_id: int):
    row = cursor.execute(
        "SELECT id, mold_id, machine_type FROM dbo.mold_machine_types WHERE id = ?",
        machine_type_id,
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="机型不存在")
    return row


@router.post("/changelog/{changelog_id}/favorite", status_code=201)
def create_favorite_from_changelog(
    changelog_id: int,
    data: FavoriteCreateRequest,
    user: dict = Depends(require_user),
):
    """Snapshot every 工艺参数 tag as it stood at the moment of a
    specific 变更记录 row, and save it against a Mold + Machine Type."""
    require_editor(user)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请输入收藏名称")

    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()

            changelog_row = cursor.execute(
                "SELECT device_id, raw_message_id, data_time FROM dbo.tech_parameter_changelog WHERE id = ?",
                changelog_id,
            ).fetchone()
            if changelog_row is None:
                raise HTTPException(status_code=404, detail="变更记录不存在")

            _get_machine_type_or_404(cursor, data.machine_type_id)

            parameters = _build_parameters_snapshot(
                cursor, changelog_row.device_id, changelog_row.raw_message_id
            )
            payload = json.dumps(parameters, ensure_ascii=False)

            existing = cursor.execute(
                "SELECT id FROM dbo.mold_favorite_snapshots WHERE machine_type_id = ? AND name = ?",
                data.machine_type_id, name,
            ).fetchone()

            if existing and not data.overwrite:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "favorite_name_exists",
                        "message": f"该机型下已存在名为「{name}」的收藏，是否覆盖？",
                    },
                )

            if existing:
                cursor.execute(
                    """
                    UPDATE dbo.mold_favorite_snapshots
                    SET device_id = ?, source_raw_message_id = ?, source_changelog_id = ?,
                        captured_data_time = ?, parameters_json = ?,
                        updated_at = SYSUTCDATETIME(), updated_by = ?
                    WHERE id = ?
                    """,
                    changelog_row.device_id,
                    changelog_row.raw_message_id,
                    changelog_id,
                    changelog_row.data_time,
                    payload,
                    user["id"],
                    existing.id,
                )
                favorite_id = existing.id
            else:
                favorite_id = cursor.execute(
                    """
                    INSERT INTO dbo.mold_favorite_snapshots
                        (machine_type_id, name, device_id, source_raw_message_id,
                         source_changelog_id, captured_data_time, parameters_json, created_by)
                    OUTPUT INSERTED.id
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    data.machine_type_id,
                    name,
                    changelog_row.device_id,
                    changelog_row.raw_message_id,
                    changelog_id,
                    changelog_row.data_time,
                    payload,
                    user["id"],
                ).fetchone()[0]

            connection.commit()
            return {"status": "ok", "id": favorite_id}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/molds/{mold_id}/machine-types/{machine_type_id}/favorites")
def list_favorites(mold_id: int, machine_type_id: int, user: dict = Depends(require_user)):
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            machine_type = _get_machine_type_or_404(cursor, machine_type_id)
            if machine_type.mold_id != mold_id:
                raise HTTPException(status_code=404, detail="机型不属于该模具")
            cursor.execute(
                """
                SELECT id, name, device_id, captured_data_time, updated_at
                FROM dbo.mold_favorite_snapshots
                WHERE machine_type_id = ?
                ORDER BY updated_at DESC
                """,
                machine_type_id,
            )
            return [row_to_dict(cursor, row) for row in cursor.fetchall()]
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/favorites/{favorite_id}")
def get_favorite(favorite_id: int, user: dict = Depends(require_user)):
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            row = cursor.execute(
                """
                SELECT id, machine_type_id, name, device_id, captured_data_time,
                       parameters_json, updated_at
                FROM dbo.mold_favorite_snapshots
                WHERE id = ?
                """,
                favorite_id,
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="收藏不存在")
            record = row_to_dict(cursor, row)
            record["parameters"] = json.loads(record.pop("parameters_json"))
            return record
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.delete("/favorites/{favorite_id}")
def delete_favorite(favorite_id: int, user: dict = Depends(require_user)):
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM dbo.mold_favorite_snapshots WHERE id = ?", favorite_id)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="收藏不存在")
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error