from contextlib import closing

import pyodbc
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from .config import FRONTEND_DIR
from .database import get_connection
from .routers import auth, changelog, devices, molds, uptime, warnings
from .security import find_session_user

class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """Prevent browsers from caching /static assets (JS/CSS/images), so
    edits to frontend files show up on a normal refresh instead of
    requiring a hard refresh to bypass a stale cached copy."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


app = FastAPI(title="注塑机 MES API", version="2.2.0")
app.add_middleware(NoCacheStaticMiddleware) 
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(molds.router)
app.include_router(changelog.router)
app.include_router(warnings.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.include_router(uptime.router)


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