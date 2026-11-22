"""FastAPI app factory: wires config, persistence, the API and the React SPA.

`create_app(config)` is the composition root: it builds the Session engine and
the realtime hub (hub subscribes to engine events) and includes their routers.
Later modules (AI Agent runner) are wired here too; keep this file thin.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import persistence
from .ai_agents import AIAgents
from .llm import make_llm_client
from .api import sessions_router
from .config import Config
from .realtime import RealtimeHub, ws_router
from .session_engine import SessionEngine

log = logging.getLogger(__name__)


def static_dir() -> Path:
    """Where the built React app lives (`npm run build` output, copied in by the Dockerfile)."""
    return Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))


def create_app(config: Config) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await persistence.create_schema(engine)
        log.info(
            "Started with condition=%s mock_mode=%s reveal_identities_at_end=%s",
            config.condition.name,
            config.mock_mode,
            config.reveal_identities_at_end,
        )
        yield
        ai_agents.shutdown()
        await session_engine.shutdown()
        await engine.dispose()

    # The async engine connects lazily, so it is safe to build before the lifespan runs.
    engine = persistence.create_engine()
    session_engine = SessionEngine(engine, config)
    hub = RealtimeHub(session_engine)  # subscribes first: browsers hear each frame before AI Agents react
    ai_agents = AIAgents(session_engine, engine, config.ai_agents, make_llm_client(config))

    app = FastAPI(title="Human-AI Group Decision Experiment", lifespan=lifespan)
    app.state.config = config
    app.state.engine = engine
    app.state.session_engine = session_engine

    app.include_router(_health_router(), prefix="/api")
    app.include_router(sessions_router(session_engine, config), prefix="/api")
    app.include_router(ws_router(hub))  # must come before the SPA catch-all
    _mount_spa(app, static_dir())
    return app


def _health_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health(request: Request):
        db_ok = await persistence.ping(request.app.state.engine)
        body = {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unreachable"}
        return JSONResponse(body, status_code=200 if db_ok else 503)

    return router


def _mount_spa(app: FastAPI, root: Path) -> None:
    """Serve the React build. Any non-API path falls back to index.html so
    client-side routes (/waiting, /room/:roomCode) work on direct visit and refresh."""
    index = root / "index.html"
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse("/waiting")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        # Unknown /api or /ws paths are real 404s, not the SPA.
        if path.startswith(("api/", "ws/")) or path in ("api", "ws"):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root.resolve()):
            return FileResponse(candidate)  # e.g. favicon, robots.txt from public/
        if not index.is_file():
            raise HTTPException(status_code=503, detail="Frontend build not found")
        return FileResponse(index)
