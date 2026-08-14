from contextlib import closing
import json
import uuid

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ..config import MOLD_UPLOAD_DIR
from ..database import get_connection, row_to_dict
from ..schemas import MoldUpdateRequest
from ..security import require_editor, require_user


router = APIRouter(prefix="/api", tags=["molds"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGES = 4


def _cavity_rows_for(cavities: int) -> list[str]:
    """['IN1','OUT1','IN2','OUT2', ...] for the given cavity count."""
    labels = []
    for i in range(1, cavities + 1):
        labels.append(f"IN{i}")
        labels.append(f"OUT{i}")
    return labels


def _parse_temperatures(raw: str | None, expected_labels: list[str]) -> dict[str, float | None]:
    """raw is a JSON string like {"IN1": 25.5, "OUT1": null, ...}. Unknown
    or missing labels default to NULL; anything not in expected_labels is
    ignored (defends against a stale/mismatched cavity count in the form)."""
    parsed = {}
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="cavity_temperatures 格式不正确") from None
    result = {}
    for label in expected_labels:
        value = parsed.get(label)
        if value in (None, ""):
            result[label] = None
        else:
            try:
                result[label] = float(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"温度值无效：{label}") from None
    return result


def _attach_images_and_temps(cursor, records: list[dict]) -> list[dict]:
    if not records:
        return records
    ids = [r["id"] for r in records]
    placeholders = ",".join("?" for _ in ids)

    cursor.execute(
        f"""
        SELECT mold_id, id, file_path, is_face, sort_order
        FROM dbo.mold_images
        WHERE mold_id IN ({placeholders})
        ORDER BY mold_id, sort_order
        """,
        ids,
    )
    images_by_mold: dict[int, list[dict]] = {}
    for row in cursor.fetchall():
        images_by_mold.setdefault(row.mold_id, []).append(
            {"id": row.id, "url": row.file_path, "is_face": bool(row.is_face)}
        )

    cursor.execute(
        f"""
        SELECT mold_id, cavity_label, temperature_c
        FROM dbo.mold_cavity_temperatures
        WHERE mold_id IN ({placeholders})
        ORDER BY mold_id, sort_order
        """,
        ids,
    )
    temps_by_mold: dict[int, list[dict]] = {}
    for row in cursor.fetchall():
        temps_by_mold.setdefault(row.mold_id, []).append(
            {"cavity_label": row.cavity_label, "temperature_c": row.temperature_c}
        )

    for record in records:
        images = images_by_mold.get(record["id"], [])
        record["images"] = images
        face = next((img for img in images if img["is_face"]), None)
        record["face_image_url"] = face["url"] if face else (images[0]["url"] if images else None)
        record["cavity_temperatures"] = temps_by_mold.get(record["id"], [])

    return records


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
            records = [row_to_dict(cursor, row) for row in cursor.fetchall()]
            return _attach_images_and_temps(cursor, records)
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/molds", status_code=201)
async def create_mold(
    user: dict = Depends(require_user),
    mold_code: str = Form(..., max_length=100),          # Project ID
    mold_name: str = Form(..., max_length=200),           # Project Name
    cavities: int = Form(..., ge=1, le=10_000),
    remark: str | None = Form(None, max_length=500),
    cavity_temperatures: str | None = Form(None),          # JSON: {"IN1": 25.0, ...}
    face_index: int = Form(0),
    images: list[UploadFile] = File(default=[]),
):
    require_editor(user)

    if len(images) < 1:
        raise HTTPException(status_code=400, detail="至少需要上传一张项目图片")
    if len(images) > MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"最多上传 {MAX_IMAGES} 张图片")
    for image in images:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的图片类型：{image.content_type}")
    if not (0 <= face_index < len(images)):
        raise HTTPException(status_code=400, detail="封面图片选择无效")

    expected_labels = _cavity_rows_for(cavities)
    temps = _parse_temperatures(cavity_temperatures, expected_labels)

    sql_insert_mold = """
        INSERT INTO dbo.molds
            (mold_code, mold_name, cavities, remark, created_by)
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?)
    """

    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold_id = cursor.execute(
                sql_insert_mold,
                mold_code.strip(),
                mold_name.strip(),
                cavities,
                remark.strip() if remark else None,
                user["id"],
            ).fetchone()[0]

            # ---- cavity temperature rows ----
            for sort_order, label in enumerate(expected_labels):
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_cavity_temperatures
                        (mold_id, cavity_label, temperature_c, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    mold_id,
                    label,
                    temps[label],
                    sort_order,
                )

            # ---- image files ----
            mold_dir = MOLD_UPLOAD_DIR / str(mold_id)
            mold_dir.mkdir(parents=True, exist_ok=True)
            for sort_order, image in enumerate(images):
                extension = (image.filename or "").rsplit(".", 1)[-1].lower() if "." in (image.filename or "") else "jpg"
                safe_name = f"{uuid.uuid4().hex}.{extension}"
                dest = mold_dir / safe_name
                content = await image.read()
                dest.write_bytes(content)
                web_path = f"/static/uploads/molds/{mold_id}/{safe_name}"
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_images
                        (mold_id, file_path, is_face, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    mold_id,
                    web_path,
                    1 if sort_order == face_index else 0,
                    sort_order,
                )

            connection.commit()
            return {"status": "ok", "id": mold_id}
    except pyodbc.IntegrityError as error:
        raise HTTPException(status_code=409, detail="项目编号已经存在") from error
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.put("/molds/{mold_id}")
def update_mold(
    mold_id: int,
    data: MoldUpdateRequest,
    user: dict = Depends(require_user),
):
    # Note: this JSON endpoint updates text fields only. Re-uploading
    # images/cavity temperatures isn't supported here yet -- do that
    # through a future dedicated endpoint if needed.
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


# ---- mount/unmount/history endpoints (unchanged) ----
@router.post("/devices/{device_id}/mold")
def mount_mold(device_id: str, data: dict, user: dict = Depends(require_user)):
    ...  # keep your existing implementation from the current file