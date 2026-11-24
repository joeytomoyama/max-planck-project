"""REST API for Sessions. Thin: every rule lives in the Session engine.

Responses carry Room Codes, statuses and Player Labels only, never
Participant types, the Condition or Human slot counts (Blind Condition): the
Room Code is in every Human's share link, so anything keyed by it alone is
public. The Researcher routes (status, manual start) need the Researcher token
that `POST /sessions` returns (header `X-Researcher-Token`).
An expired Session is refused with 410.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, Header, HTTPException, Request

from .config import Config
from .session_engine import NotWaiting, SessionEngine, SessionExpired, SessionNotFound, WrongResearcherToken


@contextmanager
def _session_errors() -> Iterator[None]:
    """Engine lookups as HTTP errors: not found -> 404, expired -> 410, not waiting -> 409,
    missing or wrong Researcher token -> 403."""
    try:
        yield
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="Session not found") from None
    except SessionExpired:
        raise HTTPException(status_code=410, detail="Session expired") from None
    except NotWaiting:
        raise HTTPException(status_code=409, detail="Session is not waiting") from None
    except WrongResearcherToken:
        raise HTTPException(status_code=403, detail="Researcher token required") from None


def sessions_router(engine: SessionEngine, config: Config) -> APIRouter:
    router = APIRouter(prefix="/sessions")

    @router.post("", status_code=201)
    async def create_session(request: Request):
        created = await engine.create_session()
        share_link = str(request.base_url).rstrip("/") + f"/room/{created.room_code}"
        return {"room_code": created.room_code, "share_link": share_link, "researcher_token": created.researcher_token}

    @router.get("/{room_code}")
    async def get_session(room_code: str):
        with _session_errors():
            return await engine.public_state(room_code)

    @router.get("/{room_code}/researcher")
    async def researcher_status(room_code: str, x_researcher_token: str | None = Header(default=None)):
        """Condition and Human slots filled/total, for the Researcher's /waiting page only."""
        with _session_errors():
            return await engine.researcher_status(room_code, x_researcher_token)

    @router.post("/{room_code}/start")
    async def start_session(room_code: str, x_researcher_token: str | None = Header(default=None)):
        """Force waiting -> active (Researcher only): the same transition as the automatic start.
        Open to Humans, its response would count the Participants of a Session started early."""
        with _session_errors():
            await engine.require_researcher(room_code, x_researcher_token)
            await engine.start(room_code)
        return await engine.public_state(room_code)

    @router.get("/{room_code}/config")
    async def session_config(room_code: str):
        """Public settings only (timings, number of Rounds). Never the Condition."""
        with _session_errors():
            await engine.ensure_exists(room_code)
        return config.public_settings()

    return router
