from contextlib import asynccontextmanager, closing

import pyodbc
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from .config import FRONTEND_DIR
from .database import get_connection
from .routers import auth, changelog, devices, favorites, molds, uptime, warnings
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with closing(get_connection()):
            pass
    except pyodbc.Error:
        pass

    yield


app = FastAPI(title="注塑机 MES API", version="2.2.0", lifespan=lifespan)
app.add_middleware(NoCacheStaticMiddleware)
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(molds.router)
app.include_router(changelog.router)
app.include_router(warnings.router)
app.include_router(favorites.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.include_router(uptime.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/login")
def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str, request: Request):
    user = find_session_user(request)
    if user is None:
        return RedirectResponse("/login")
    return FileResponse(FRONTEND_DIR / "index.html")