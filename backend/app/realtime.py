"""Realtime hub: the one WebSocket endpoint `/ws/{room_code}`.

It owns the sockets, keeps them per Session, forwards client frames to the
Session engine and turns engine `Event`s into JSON frames. It holds no game
state of its own. Frames only ever carry Player Labels (Blind Condition).

Protocol (JSON, every frame has a `type`):
  client -> server: join   (later: chat, vote)
  server -> client: joined, waiting, error   (later: phase, chat, vote_recorded, result)
A refused join gets an `error` frame with a `reason`, then a close with a
4xxx code (see CLOSE_CODES), so a client can show the right error view.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .session_engine import Event, JoinedParticipant, JoinRefused, SessionEngine

log = logging.getLogger(__name__)

CLOSE_CODES = {
    "not_found": 4404,
    "full": 4409,
    "active": 4423,
    "completed": 4410,
    "expired": 4408,
    "bad_request": 4400,
}


class RealtimeHub:
    def __init__(self, engine: SessionEngine):
        self._engine = engine
        # room_code -> participant id -> socket
        self._sockets: dict[str, dict[int, WebSocket]] = defaultdict(dict)
        engine.subscribe(self._on_event)

    async def _on_event(self, event: Event) -> None:
        room = self._sockets.get(event.room_code, {})
        if event.recipient is None:
            targets = list(room.values())
        else:
            targets = [room[event.recipient]] if event.recipient in room else []
        for ws in targets:
            try:
                await ws.send_json(event.payload)
            except Exception:  # noqa: BLE001 - socket already closing; its handler cleans up
                log.debug("Send failed on a closing socket")

    async def handle(self, ws: WebSocket, room_code: str) -> None:
        await ws.accept()
        try:
            first = await ws.receive_json()
        except (WebSocketDisconnect, ValueError):
            return
        if not isinstance(first, dict) or first.get("type") != "join":
            await _refuse(ws, "bad_request")
            return
        try:
            participant = await self._engine.join(room_code)
        except JoinRefused as refused:
            await _refuse(ws, refused.reason)
            return

        self._sockets[room_code][participant.id] = ws
        try:
            await self._engine.connected(participant)
            await self._receive_loop(ws, participant)
        except WebSocketDisconnect:
            pass
        finally:
            self._sockets[room_code].pop(participant.id, None)
            if not self._sockets[room_code]:
                self._sockets.pop(room_code, None)
            await self._engine.disconnected(participant)

    async def _receive_loop(self, ws: WebSocket, participant: JoinedParticipant) -> None:
        while True:
            try:
                frame = await ws.receive_json()
            except ValueError:
                await ws.send_json({"type": "error", "reason": "bad_request"})
                continue
            # chat / vote frames are routed to the engine in tickets #12/#13.
            kind = frame.get("type") if isinstance(frame, dict) else None
            await ws.send_json({"type": "error", "reason": "unsupported", "detail": str(kind)[:32]})


async def _refuse(ws: WebSocket, reason: str) -> None:
    await ws.send_json({"type": "error", "reason": reason})
    await ws.close(code=CLOSE_CODES.get(reason, 4400))


def ws_router(hub: RealtimeHub) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/{room_code}")
    async def room_socket(ws: WebSocket, room_code: str):
        await hub.handle(ws, room_code)

    return router
