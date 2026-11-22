"""REST API for Sessions. Thin: every rule lives in the Session engine.

Responses carry Room Codes, statuses and Player Labels only, never
Participant types (Blind Condition).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .session_engine import SessionEngine, SessionNotFound


def sessions_router(engine: SessionEngine) -> APIRouter:
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

    return router
