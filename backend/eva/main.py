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


def _apply_activation_profile() -> None:
    """Apply the EVA_PROFILE activation profile at startup.

    Default profile is 'safe' (a pure no-op), so unless an operator opts into a
    profile this is byte-identical to before. A profile only ever fills in
    unset capability flags and never auto-enables real input, browser, or MCP.
    Wrapped so a bad EVA_PROFILE value can never block or crash startup."""
    try:
        from .runtime.activation import activate_profile

        activate_profile()
    except Exception:
        pass


def _recover_durable_tasks_if_enabled(app: FastAPI) -> None:
    """Resume durable work after a crash/reboot (Phase 45), only when
    EVA_DURABLE_QUEUE_ENABLED is set. Recovery only re-queues interrupted
    requests — each re-run still faces the permission gate, so nothing
    privileged is replayed unattended. This never auto-drains the queue; a
    worker is a separate, opt-in step. Wrapped so it can never crash startup."""
    try:
        from .tasks import open_default_queue

        queue = open_default_queue()
        if queue is None:
            return
        app.state.task_queue = queue
        app.state.task_recovery = queue.recover_orphans()
    except Exception:
        pass


def _run_proactivity_catchup_if_enabled(app: FastAPI) -> None:
    """Evaluate standing proactive rules once at startup (Phase 46), only when
    EVA_PROACTIVITY_ENABLED is set.

    This is the catch-up pass: whatever became due while Eva was off gets
    PROPOSED now. A tick only enqueues requests and records notifications — it
    executes nothing, so everything it proposes still faces the permission gate
    before it can run. No background loop is started here; ticking beyond this
    catch-up is a deliberate call. Wrapped so it can never crash startup."""
    try:
        from .proactivity import open_default_engine

        engine = open_default_engine()
        if engine is None:
            return
        app.state.proactivity = engine
        app.state.proactivity_catchup = engine.tick()
    except Exception:
        pass


def create_app() -> FastAPI:
    load_project_env(ROOT)
    _apply_activation_profile()
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
    _recover_durable_tasks_if_enabled(app)
    _run_proactivity_catchup_if_enabled(app)
    app.include_router(router, prefix="/api")
    app.include_router(get_control_center_routes())
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
