from contextlib import closing

import pyodbc
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR
from .database import get_connection
from .routers import auth, devices, molds
from .security import find_session_user


app = FastAPI(title="注塑机 MES API", version="2.1.0")
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(molds.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/health")
def health_check():
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ok", "database": "connected"}
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if find_session_user(request):
        return RedirectResponse("/", status_code=303)
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/", include_in_schema=False)
def dashboard(request: Request):
    if not find_session_user(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(FRONTEND_DIR / "index.html")
