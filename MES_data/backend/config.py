import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"

MOLD_UPLOAD_DIR = FRONTEND_DIR / "uploads" / "molds"
MOLD_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TRIAL_TEMPLATE_DIR = FRONTEND_DIR / "uploads" / "trial_templates"
TRIAL_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

# Global fallback workbook used by GET .../export whenever a Mold +
# Machine Type has no user-uploaded template on file (see
# backend/template_storage.py for the per-machine-type override). This
# is a real, correctly-formatted blank copy of the company's 试模成型
#参数表, checked into the repo -- export always writes into a copy of
# THIS file via overlay_values_onto_template() rather than regenerating
# a sheet from the embedded static _TEMPLATE in export_xlsx.py, so
# formatting is correct even before anyone has ever uploaded anything
# for a given machine type.
DEFAULT_TRIAL_TEMPLATE_PATH = PROJECT_DIR / "backend" / "assets" / "default_trial_template.xlsx"

SESSION_COOKIE = "mes_session"
SESSION_HOURS = 12
PBKDF2_ITERATIONS = 310_000

SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server")
SQL_SERVER = os.getenv("SQL_SERVER", r"localhost\SQLDEVELOP")
SQL_DATABASE = os.getenv("SQL_DATABASE", "MES_MQTT")
SQL_USERNAME = os.getenv("SQL_USERNAME", "")
SQL_PASSWORD = os.getenv("SQL_PASSWORD", "")
SQL_POOL_SIZE = int(os.getenv("SQL_POOL_SIZE", "8"))


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


SQL_CONNECTION_STRING = build_connection_string()