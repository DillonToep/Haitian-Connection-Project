from contextlib import closing
import json
import uuid

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ..config import MOLD_UPLOAD_DIR
from ..database import get_connection, row_to_dict
from ..security import require_editor, require_user
from ..parameter_labels import PARAMETER_LABELS, categorize
from ..schemas import (
    MoldAssignmentRequest,
    MoldParametersUpdateRequest,
    MoldUpdateRequest,
)


router = APIRouter(prefix="/api", tags=["molds"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGES = 4


def _cavity_rows_for(cavities: int) -> list[str]:
    """['1', '2', ..., str(cavities)] -- one temperature entry per item."""
    return [str(i) for i in range(1, cavities + 1)]


def _parse_cavity_values(raw: str | None, expected_labels: list[str]) -> dict[str, dict[str, float | None]]:
    """raw is a JSON string like
    {"1": {"temperature_c": 25.5, "tolerance_pct": 5}, "2": {...}}.
    Unknown/missing labels default to NULL; anything not in
    expected_labels is ignored (defends against a stale/mismatched
    cavity count in the form)."""
    parsed = {}
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="cavity_temperatures 格式不正确") from None

    def _as_float(value, label):
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"数值无效：{label}") from None

    result = {}
    for label in expected_labels:
        entry = parsed.get(label)
        if entry is None:
            entry = {}
        elif not isinstance(entry, dict):
            # Back-compat: old shape was label -> temperature number only.
            entry = {"temperature_c": entry}
        result[label] = {
            "temperature_c": _as_float(entry.get("temperature_c"), label),
            "tolerance_pct": _as_float(entry.get("tolerance_pct"), label),
        }
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
        SELECT mold_id, cavity_label, temperature_c, tolerance_pct
        FROM dbo.mold_cavity_temperatures
        WHERE mold_id IN ({placeholders})
        ORDER BY mold_id, sort_order
        """,
        ids,
    )
    temps_by_mold: dict[int, list[dict]] = {}
    for row in cursor.fetchall():
        temps_by_mold.setdefault(row.mold_id, []).append(
            {
                "cavity_label": row.cavity_label,
                "temperature_c": row.temperature_c,
                "tolerance_pct": row.tolerance_pct,
            }
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


@router.get("/molds/parameter-defaults")
def get_mold_parameter_defaults(user: dict = Depends(require_user)):
    """The global 高级工艺参数 template used to seed every *new* mold going
    forward (see create_mold below). Registered before
    /molds/{mold_id}/parameters so the literal 'parameter-defaults' path
    segment isn't swallowed by that route's int-typed mold_id."""
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat "
                "FROM dbo.mold_parameter_defaults"
            )
            saved = {row.parameter_id: row for row in cursor.fetchall()}
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    parameters = []
    for tag, meta in PARAMETER_LABELS.items():
        if not meta["use"]:
            continue
        row = saved.get(tag)
        parameters.append(
            {
                "parameter_id": tag,
                "label": meta["label"],
                "category": categorize(meta["label"]),
                "value": row.target_value if row else None,
                "tolerance_mode": row.tolerance_mode if row else "percent",
                "tolerance_percent": float(row.tolerance_percent) if row and row.tolerance_percent is not None else None,
                "tolerance_flat": float(row.tolerance_flat) if row and row.tolerance_flat is not None else None,
            }
        )
    return {"parameters": parameters}


@router.put("/molds/parameter-defaults")
def update_mold_parameter_defaults(
    data: MoldParametersUpdateRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    valid_tags = set(PARAMETER_LABELS.keys())
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM dbo.mold_parameter_defaults")
            for item in data.parameters:
                if item.parameter_id not in valid_tags:
                    continue
                value = item.value.strip() if item.value else None
                tol_percent = item.tolerance_percent if item.tolerance_mode == "percent" else None
                tol_flat = item.tolerance_flat if item.tolerance_mode == "flat" else None
                if not value and tol_percent is None and tol_flat is None:
                    continue  # blank row, nothing worth saving as a default
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_parameter_defaults
                        (parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat, updated_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    item.parameter_id,
                    value,
                    item.tolerance_mode,
                    tol_percent,
                    tol_flat,
                    user["id"],
                )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/molds/{mold_id}/parameters")
def get_mold_parameters(mold_id: int, user: dict = Depends(require_user)):
    del user
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在")
            cursor.execute(
                "SELECT parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat "
                "FROM dbo.mold_parameter_targets WHERE mold_id = ?",
                mold_id,
            )
            saved = {row.parameter_id: row for row in cursor.fetchall()}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    parameters = []
    for tag, meta in PARAMETER_LABELS.items():
        if not meta["use"]:
            continue
        row = saved.get(tag)
        parameters.append(
            {
                "parameter_id": tag,
                "label": meta["label"],
                "category": categorize(meta["label"]),
                "value": row.target_value if row else None,
                "tolerance_mode": row.tolerance_mode if row else "percent",
                "tolerance_percent": float(row.tolerance_percent) if row and row.tolerance_percent is not None else None,
                "tolerance_flat": float(row.tolerance_flat) if row and row.tolerance_flat is not None else None,
            }
        )
    return {"mold_id": mold_id, "parameters": parameters}


@router.put("/molds/{mold_id}/parameters")
def update_mold_parameters(
    mold_id: int,
    data: MoldParametersUpdateRequest,
    user: dict = Depends(require_user),
):
    require_editor(user)
    valid_tags = set(PARAMETER_LABELS.keys())
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            cursor.execute("DELETE FROM dbo.mold_parameter_targets WHERE mold_id = ?", mold_id)
            for item in data.parameters:
                if item.parameter_id not in valid_tags:
                    continue
                value = item.value.strip() if item.value else None
                tol_percent = item.tolerance_percent if item.tolerance_mode == "percent" else None
                tol_flat = item.tolerance_flat if item.tolerance_mode == "flat" else None
                if not value and tol_percent is None and tol_flat is None:
                    continue  # blank row, nothing to save
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_parameter_targets
                        (mold_id, parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    mold_id,
                    item.parameter_id,
                    value,
                    item.tolerance_mode,
                    tol_percent,
                    tol_flat,
                )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error



@router.post("/molds", status_code=201)
async def create_mold(
    user: dict = Depends(require_user),
    mold_code: str = Form(..., max_length=100),
    mold_name: str = Form(..., max_length=200),
    cavities: int = Form(..., ge=1, le=10_000),
    remark: str | None = Form(None, max_length=500),
    cavity_temperatures: str | None = Form(None),
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
    temps = _parse_cavity_values(cavity_temperatures, expected_labels)

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

            for sort_order, label in enumerate(expected_labels):
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_cavity_temperatures
                        (mold_id, cavity_label, temperature_c, tolerance_pct, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    mold_id,
                    label,
                    temps[label]["temperature_c"],
                    temps[label]["tolerance_pct"],
                    sort_order,
                )

            # ---- seed 高级工艺参数 from the global defaults template, if
            # any have been configured (模具管理 -> 默认参数设置). Only
            # affects this brand-new mold; existing molds are untouched. ----
            cursor.execute(
                "SELECT parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat "
                "FROM dbo.mold_parameter_defaults"
            )
            for default_row in cursor.fetchall():
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_parameter_targets
                        (mold_id, parameter_id, target_value, tolerance_mode, tolerance_percent, tolerance_flat)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    mold_id,
                    default_row.parameter_id,
                    default_row.target_value,
                    default_row.tolerance_mode,
                    default_row.tolerance_percent,
                    default_row.tolerance_flat,
                )

            # ---- image files (runs once, not once-per-cavity) ----
            mold_dir = MOLD_UPLOAD_DIR / str(mold_id)
            mold_dir.mkdir(parents=True, exist_ok=True)
            for image_index, image in enumerate(images):
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
                    1 if image_index == face_index else 0,
                    image_index,
                )

            connection.commit()
            return {"status": "ok", "id": mold_id}
    except pyodbc.IntegrityError as error:
        raise HTTPException(status_code=409, detail="项目编号已经存在") from error
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.put("/molds/{mold_id}")
async def update_mold(
    mold_id: int,
    user: dict = Depends(require_user),
    mold_code: str = Form(..., max_length=100),
    mold_name: str = Form(..., max_length=200),
    cavities: int = Form(..., ge=1, le=10_000),
    remark: str | None = Form(None, max_length=500),
    is_active: str = Form("1"),
    cavity_temperatures: str | None = Form(None),
    keep_image_ids: str | None = Form(None),   # JSON array of existing image ids to keep
    face_image_id: int | None = Form(None),    # id of a kept existing image to use as cover
    face_new_index: int | None = Form(None),   # index within the new `images` list to use as cover
    images: list[UploadFile] = File(default=[]),
):
    require_editor(user)

    for image in images:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的图片类型：{image.content_type}")

    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM dbo.molds WHERE id = ?", mold_id)
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="模具不存在")

            cursor.execute(
                "SELECT id, file_path, is_face FROM dbo.mold_images WHERE mold_id = ? ORDER BY sort_order",
                mold_id,
            )
            existing_images = [
                {"id": row.id, "file_path": row.file_path, "is_face": bool(row.is_face)}
                for row in cursor.fetchall()
            ]

            if keep_image_ids is not None:
                try:
                    keep_ids = set(json.loads(keep_image_ids))
                except json.JSONDecodeError:
                    raise HTTPException(status_code=400, detail="keep_image_ids 格式不正确") from None
            else:
                # Not provided -- text-only edit that doesn't touch images at all.
                keep_ids = {img["id"] for img in existing_images}

            kept_images = [img for img in existing_images if img["id"] in keep_ids]
            removed_images = [img for img in existing_images if img["id"] not in keep_ids]

            total_images = len(kept_images) + len(images)
            if total_images < 1:
                raise HTTPException(status_code=400, detail="至少需要保留一张项目图片")
            if total_images > MAX_IMAGES:
                raise HTTPException(status_code=400, detail=f"最多上传 {MAX_IMAGES} 张图片")

            expected_labels = _cavity_rows_for(cavities)
            temps = _parse_cavity_values(cavity_temperatures, expected_labels)

            # ---- text fields ----
            cursor.execute(
                """
                UPDATE dbo.molds
                SET mold_code = ?, mold_name = ?, cavities = ?, remark = ?,
                    is_active = ?, updated_at = SYSDATETIME()
                WHERE id = ?
                """,
                mold_code.strip(),
                mold_name.strip(),
                cavities,
                remark.strip() if remark else None,
                1 if is_active == "1" else 0,
                mold_id,
            )

            # ---- cavity temperatures: replace wholesale, same as create ----
            cursor.execute("DELETE FROM dbo.mold_cavity_temperatures WHERE mold_id = ?", mold_id)
            for sort_order, label in enumerate(expected_labels):
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_cavity_temperatures
                        (mold_id, cavity_label, temperature_c, tolerance_pct, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    mold_id,
                    label,
                    temps[label]["temperature_c"],
                    temps[label]["tolerance_pct"],
                    sort_order,
                )

            # ---- removed images: delete rows + files on disk ----
            for img in removed_images:
                cursor.execute("DELETE FROM dbo.mold_images WHERE id = ?", img["id"])
                filename = img["file_path"].rsplit("/", 1)[-1]
                disk_path = MOLD_UPLOAD_DIR / str(mold_id) / filename
                try:
                    disk_path.unlink(missing_ok=True)
                except OSError:
                    pass

            # ---- kept images: reassign sort order + cover flag ----
            for sort_order, img in enumerate(kept_images):
                is_face = 1 if (face_image_id is not None and img["id"] == face_image_id) else 0
                cursor.execute(
                    "UPDATE dbo.mold_images SET is_face = ?, sort_order = ? WHERE id = ?",
                    is_face,
                    sort_order,
                    img["id"],
                )

            # ---- newly uploaded images ----
            mold_dir = MOLD_UPLOAD_DIR / str(mold_id)
            mold_dir.mkdir(parents=True, exist_ok=True)
            for new_index, image in enumerate(images):
                extension = (image.filename or "").rsplit(".", 1)[-1].lower() if "." in (image.filename or "") else "jpg"
                safe_name = f"{uuid.uuid4().hex}.{extension}"
                dest = mold_dir / safe_name
                content = await image.read()
                dest.write_bytes(content)
                web_path = f"/static/uploads/molds/{mold_id}/{safe_name}"
                is_face = 1 if (face_new_index is not None and new_index == face_new_index) else 0
                cursor.execute(
                    """
                    INSERT INTO dbo.mold_images
                        (mold_id, file_path, is_face, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    mold_id,
                    web_path,
                    is_face,
                    len(kept_images) + new_index,
                )

            # ---- safety net: guarantee exactly one cover image ----
            cursor.execute(
                "SELECT COUNT(*) FROM dbo.mold_images WHERE mold_id = ? AND is_face = 1",
                mold_id,
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    """
                    UPDATE dbo.mold_images SET is_face = 1
                    WHERE id = (
                        SELECT TOP 1 id FROM dbo.mold_images
                        WHERE mold_id = ? ORDER BY sort_order
                    )
                    """,
                    mold_id,
                )

            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.IntegrityError as error:
        raise HTTPException(status_code=409, detail="项目编号已经存在") from error
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@router.get("/devices/{device_id}/mold")
def get_current_mold(device_id: str, user: dict = Depends(require_user)):
    """The device's currently active mold assignment, or null if none."""
    del user
    sql = """
        SELECT TOP 1
            a.id AS assignment_id, a.mounted_at, a.remark,
            m.id AS mold_id, m.mold_code, m.mold_name,
            m.product_code, m.cavities
        FROM dbo.device_mold_assignments AS a
        INNER JOIN dbo.molds AS m ON m.id = a.mold_id
        WHERE a.device_id = ? AND a.unmounted_at IS NULL
        ORDER BY a.mounted_at DESC
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            row = cursor.fetchone()
            return row_to_dict(cursor, row) if row else None
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/devices/{device_id}/mold")
def assign_mold(
    device_id: str,
    data: MoldAssignmentRequest,
    user: dict = Depends(require_user),
):
    """Assign (mount) a mold onto a device. Since dbo.device_mold_assignments
    only allows one active row per device AND one active row per mold
    (see UX_device_mold_active_device / UX_device_mold_active_mold in
    setup_web_database.sql), this both:
      1) unmounts whatever is currently on this device, and
      2) unmounts this mold from wherever else it's currently active --
         effectively "transferring" it here, rather than erroring, since
         moving a mold between machines is a normal shop-floor operation.
    """
    require_editor(user)
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            mold = cursor.execute(
                "SELECT id, is_active FROM dbo.molds WHERE id = ?", data.mold_id
            ).fetchone()
            if mold is None:
                raise HTTPException(status_code=404, detail="模具不存在")
            if not mold.is_active:
                raise HTTPException(status_code=400, detail="该模具已停用，无法分配")

            cursor.execute(
                """
                UPDATE dbo.device_mold_assignments
                SET unmounted_at = SYSDATETIME()
                WHERE device_id = ? AND unmounted_at IS NULL
                """,
                device_id,
            )
            cursor.execute(
                """
                UPDATE dbo.device_mold_assignments
                SET unmounted_at = SYSDATETIME()
                WHERE mold_id = ? AND unmounted_at IS NULL
                """,
                data.mold_id,
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
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.delete("/devices/{device_id}/mold")
def unmount_mold(device_id: str, user: dict = Depends(require_user)):
    require_editor(user)
    sql = """
        UPDATE dbo.device_mold_assignments
        SET unmounted_at = SYSDATETIME()
        WHERE device_id = ? AND unmounted_at IS NULL
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="该设备当前未装模")
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
        SELECT
            a.id, a.mold_id, m.mold_code, m.mold_name,
            a.mounted_at, a.unmounted_at, a.remark,
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