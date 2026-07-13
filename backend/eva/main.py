from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .control_center.routes import get_control_center_routes
from .core.config import load_project_env, load_settings
from .memory.store import MemoryStore


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"


def _load_mcp_tools_if_enabled() -> None:
    """Discover and register MCP tools at startup, only when EVA_MCP_ENABLED is
    set and servers are configured. Wrapped so a slow or broken MCP server can
    never block or crash app startup; MCP is entirely optional."""
    try:
        from .mcp.config import mcp_enabled

        if not mcp_enabled():
            return
        from .api import routes as _routes
        from .mcp.registration import load_mcp_tools

        load_mcp_tools(_routes.tools)
    except Exception:
        pass


def create_app() -> FastAPI:
    load_project_env(ROOT)
    _load_mcp_tools_if_enabled()
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
    app.include_router(get_control_center_routes())
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
