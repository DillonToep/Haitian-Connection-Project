"""
Add a new user to dbo.app_users using the same password hashing
scheme as backend/security.py (PBKDF2-HMAC-SHA256, 310,000 iterations).

Usage:
    python add_user.py

You will be prompted for username, password, and role.
Run this from the project root (so it can import backend.security/config),
or adjust the SQL_CONNECTION_STRING below to match your setup manually.
"""

import getpass
import secrets

import pyodbc

# ---- Match these to backend/config.py ----
SQL_DRIVER = "ODBC Driver 17 for SQL Server"
SQL_SERVER = r"localhost\SQLDEVELOP"
SQL_DATABASE = "MES_MQTT"
SQL_USERNAME = ""   # leave blank to use Trusted_Connection
SQL_PASSWORD = ""

PBKDF2_ITERATIONS = 310_000
VALID_ROLES = {"admin", "operator", "viewer"}


def build_connection_string() -> str:
    parts = [
        f"DRIVER={{{SQL_DRIVER}}}",
        f"SERVER={SQL_SERVER}",
        f"DATABASE={SQL_DATABASE}",
        "TrustServerCertificate=yes",
    ]
    if SQL_USERNAME:
        parts.extend([f"UID={SQL_USERNAME}", f"PWD={SQL_PASSWORD}"])
    else:
        parts.append("Trusted_Connection=yes")
    return ";".join(parts) + ";"


def password_digest(password: str, salt: bytes) -> bytes:
    import hashlib
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )


def main():
    username = input("Username: ").strip()
    if not username:
        raise SystemExit("Username cannot be empty.")

    role = input(f"Role {sorted(VALID_ROLES)} [operator]: ").strip() or "operator"
    if role not in VALID_ROLES:
        raise SystemExit(f"Role must be one of {sorted(VALID_ROLES)}")

    password = getpass.getpass("Password: ")
    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        raise SystemExit("Passwords do not match.")
    if len(password) < 8:
        raise SystemExit("Password should be at least 8 characters.")

    salt = secrets.token_bytes(16)
    digest = password_digest(password, salt)

    conn = pyodbc.connect(build_connection_string())
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM dbo.app_users WHERE username = ?", username
        )
        if cursor.fetchone():
            raise SystemExit(f"User '{username}' already exists.")

        cursor.execute(
            """
            INSERT INTO dbo.app_users
                (username, password_hash, password_salt, role, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            username,
            pyodbc.Binary(digest),
            pyodbc.Binary(salt),
            role,
        )
        conn.commit()
        print(f"User '{username}' created with role '{role}'.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()