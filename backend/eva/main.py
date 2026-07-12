from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .api.websocket import websocket_router
from .control_center.routes import get_control_center_routes
from .core.config import load_project_env, load_settings
from .memory.store import MemoryStore


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"


def create_app() -> FastAPI:
    load_project_env(ROOT)
    settings = load_settings(ROOT / "config" / "eva.toml")
    app = FastAPI(title="Eva Agent", version="0.1.0")
    app.state.settings = settings

    @app.middleware("http")
    async def require_client_header(request: Request, call_next):
        # State-changing requests must carry the custom X-Eva-Client header.
        # Cross-origin pages cannot add custom headers without a CORS preflight
        # (which this app never grants), so this blocks browser-based CSRF.
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.headers.get("x-eva-client"):
            return JSONResponse(status_code=403, content={"detail": "Missing X-Eva-Client header."})
        return await call_next(request)

    app.state.memory = MemoryStore(ROOT / "data" / "eva.sqlite3")
    app.include_router(router, prefix="/api")
    app.include_router(websocket_router)
    app.include_router(get_control_center_routes())
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
