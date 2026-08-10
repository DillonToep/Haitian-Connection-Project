from contextlib import closing
from datetime import datetime, timedelta
import secrets

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import SESSION_COOKIE, SESSION_HOURS
from ..database import get_connection
from ..schemas import ChangePasswordRequest, LoginRequest
from ..security import (
    password_digest,
    require_user,
    session_digest,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/login")
def login(data: LoginRequest):
    sql = """
        SELECT id, username, password_hash, password_salt, role, is_active
        FROM dbo.app_users
        WHERE username = ?
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, data.username.strip())
            row = cursor.fetchone()

            valid = bool(
                row
                and row.is_active
                and verify_password(
                    data.password,
                    bytes(row.password_hash),
                    bytes(row.password_salt),
                )
            )
            if not valid:
                raise HTTPException(status_code=401, detail="用户名或密码错误")

            token = secrets.token_urlsafe(48)
            expires_at = datetime.utcnow() + timedelta(hours=SESSION_HOURS)
            cursor.execute(
                "DELETE FROM dbo.app_sessions WHERE expires_at <= SYSUTCDATETIME()"
            )
            cursor.execute(
                "INSERT INTO dbo.app_sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                pyodbc.Binary(session_digest(token)),
                row.id,
                expires_at,
            )
            connection.commit()

            response = JSONResponse(
                {
                    "status": "ok",
                    "user": {
                        "id": row.id,
                        "username": row.username,
                        "role": row.role,
                    },
                }
            )
            response.set_cookie(
                SESSION_COOKIE,
                token,
                max_age=SESSION_HOURS * 3600,
                httponly=True,
                samesite="lax",
                secure=False,
                path="/",
            )
            return response
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            with closing(get_connection()) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "DELETE FROM dbo.app_sessions WHERE token_hash = ?",
                    pyodbc.Binary(session_digest(token)),
                )
                connection.commit()
        except pyodbc.Error:
            pass

    response = JSONResponse({"status": "ok"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me")
def current_user(user: dict = Depends(require_user)):
    return user


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    user: dict = Depends(require_user),
):
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT password_hash, password_salt FROM dbo.app_users WHERE id = ?",
                user["id"],
            )
            row = cursor.fetchone()
            if not verify_password(
                data.current_password,
                bytes(row.password_hash),
                bytes(row.password_salt),
            ):
                raise HTTPException(status_code=400, detail="当前密码不正确")

            salt = secrets.token_bytes(16)
            digest = password_digest(data.new_password, salt)
            cursor.execute(
                """
                UPDATE dbo.app_users
                SET password_hash = ?, password_salt = ?, updated_at = SYSUTCDATETIME()
                WHERE id = ?
                """,
                pyodbc.Binary(digest),
                pyodbc.Binary(salt),
                user["id"],
            )
            connection.commit()
            return {"status": "ok"}
    except HTTPException:
        raise
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
