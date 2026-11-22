"""REST API for Sessions. Thin: every rule lives in the Session engine.

Responses carry Room Codes, statuses and Player Labels only, never
Participant types (Blind Condition). An expired Session is refused with 410.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, HTTPException, Request

from .config import Config
from .session_engine import NotWaiting, SessionEngine, SessionExpired, SessionNotFound


@contextmanager
def _session_errors() -> Iterator[None]:
    """Engine lookups as HTTP errors: not found -> 404, expired -> 410, not waiting -> 409."""
    try:
        yield
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="Session not found") from None
    except SessionExpired:
        raise HTTPException(status_code=410, detail="Session expired") from None
    except NotWaiting:
        raise HTTPException(status_code=409, detail="Session is not waiting") from None


def sessions_router(engine: SessionEngine, config: Config) -> APIRouter:
    router = APIRouter(prefix="/sessions")

    @router.post("", status_code=201)
    async def create_session(request: Request):
        room_code = await engine.create_session()
        share_link = str(request.base_url).rstrip("/") + f"/room/{room_code}"
        return {"room_code": room_code, "share_link": share_link}

    @router.get("/{room_code}")
    async def get_session(room_code: str):
        with _session_errors():
            return await engine.public_state(room_code)

    @router.post("/{room_code}/start")
    async def start_session(room_code: str):
        """Force waiting -> active: the same transition as the automatic start."""
        with _session_errors():
            await engine.start(room_code)
        return await engine.public_state(room_code)

    @router.get("/{room_code}/config")
    async def session_config(room_code: str):
        """Public settings only (timings, number of Rounds). Never the Condition."""
        with _session_errors():
            await engine.ensure_exists(room_code)
        return config.public_settings()

    return router
