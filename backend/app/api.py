"""REST API for Sessions. Thin: every rule lives in the Session engine.

Responses carry Room Codes, statuses and Player Labels only, never
Participant types (Blind Condition).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .config import Config
from .session_engine import NotWaiting, SessionEngine, SessionNotFound


def sessions_router(engine: SessionEngine, config: Config) -> APIRouter:
    router = APIRouter(prefix="/sessions")

    @router.post("", status_code=201)
    async def create_session(request: Request):
        room_code = await engine.create_session()
        share_link = str(request.base_url).rstrip("/") + f"/room/{room_code}"
        return {"room_code": room_code, "share_link": share_link}

    @router.get("/{room_code}")
    async def get_session(room_code: str):
        try:
            return await engine.public_state(room_code)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="Session not found") from None

    @router.post("/{room_code}/start")
    async def start_session(room_code: str):
        """Force waiting -> active: the same transition as the automatic start."""
        try:
            await engine.start(room_code)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="Session not found") from None
        except NotWaiting:
            raise HTTPException(status_code=409, detail="Session is not waiting") from None
        return await engine.public_state(room_code)

    @router.get("/{room_code}/config")
    async def session_config(room_code: str):
        """Public settings only (timings, number of Rounds). Never the Condition."""
        try:
            await engine.ensure_exists(room_code)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="Session not found") from None
        return config.public_settings()

    return router
