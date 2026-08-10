from contextlib import closing
import hashlib
import hmac

import pyodbc
from fastapi import HTTPException, Request

from .config import PBKDF2_ITERATIONS, SESSION_COOKIE
from .database import get_connection, row_to_dict


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )


def verify_password(password: str, expected: bytes, salt: bytes) -> bool:
    actual = password_digest(password, salt)
    return hmac.compare_digest(expected, actual)


def session_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def find_session_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    sql = """
        SELECT u.id, u.username, u.role
        FROM dbo.app_sessions AS s
        INNER JOIN dbo.app_users AS u ON u.id = s.user_id
        WHERE s.token_hash = ?
          AND s.expires_at > SYSUTCDATETIME()
          AND u.is_active = 1
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, pyodbc.Binary(session_digest(token)))
            row = cursor.fetchone()
            return row_to_dict(cursor, row) if row else None
    except pyodbc.Error:
        return None


def require_user(request: Request):
    user = find_session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_editor(user: dict):
    if user["role"] not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="当前账号没有修改权限")
