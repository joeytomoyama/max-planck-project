"""Black-box checks for the Researcher token and the Blind Condition in the Waiting Room (#19).

They talk to a running app over HTTP and WebSocket, like a browser would, so
they need the stack up first (see TESTING.md, "Automated checks"):

    APP_URL=http://localhost:8000 pytest backend/tests

Works under any Condition; checks that need two Humans skip under 1_human_2_ai.
Each test creates its own Sessions and leaves them to expire.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest
import websockets

APP_URL = os.environ.get("APP_URL", "http://localhost:8000").rstrip("/")
WS_URL = APP_URL.replace("http", "ws", 1)
TOKEN_HEADER = "X-Researcher-Token"


def create_session() -> dict:
    res = httpx.post(f"{APP_URL}/api/sessions")
    assert res.status_code == 201
    return res.json()


def researcher_status(room_code: str, token: str | None) -> httpx.Response:
    headers = {TOKEN_HEADER: token} if token is not None else {}
    return httpx.get(f"{APP_URL}/api/sessions/{room_code}/researcher", headers=headers)


async def join(room_code: str):
    """Open a Human's socket and join; return it with every frame up to `waiting`."""
    ws = await websockets.connect(f"{WS_URL}/ws/{room_code}")
    await ws.send(json.dumps({"type": "join"}))
    frames = []
    while not frames or frames[-1]["type"] != "waiting":
        frames.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=5)))
    return ws, frames


async def frames_within(ws, seconds: float) -> list[dict]:
    frames = []
    try:
        while True:
            frames.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=seconds)))
    except asyncio.TimeoutError:
        return frames


# --- Researcher token ------------------------------------------------------


def test_create_returns_a_researcher_token_that_is_not_in_the_share_link():
    created = create_session()
    token = created["researcher_token"]
    assert len(token) >= 20
    assert token not in created["share_link"]


def test_researcher_status_is_refused_without_a_token():
    created = create_session()
    assert researcher_status(created["room_code"], None).status_code == 403


def test_researcher_status_is_refused_with_a_wrong_token():
    created = create_session()
    other = create_session()
    assert researcher_status(created["room_code"], "not-the-token").status_code == 403
    assert researcher_status(created["room_code"], "").status_code == 403
    # Another Session's token does not open this one.
    assert researcher_status(created["room_code"], other["researcher_token"]).status_code == 403


def test_researcher_status_gives_condition_and_slots_with_the_right_token():
    created = create_session()
    res = researcher_status(created["room_code"], created["researcher_token"])
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "waiting"
    assert body["filled"] == 0
    condition = body["condition"]
    assert condition["humans"] + condition["ai_agents"] == 3
    assert body["total"] == condition["humans"]
    assert condition["description"] in ("3 Humans", "2 Humans + 1 AI Agent", "1 Human + 2 AI Agents")


def test_researcher_status_for_an_unknown_room_code_is_not_found():
    assert researcher_status("no-such-room", "whatever").status_code == 404


# --- What a Human sees ---------------------------------------------------------


def test_public_session_routes_carry_no_condition_or_slot_count():
    created = create_session()
    for path in (f"/api/sessions/{created['room_code']}", f"/api/sessions/{created['room_code']}/config"):
        body = httpx.get(f"{APP_URL}{path}").json()
        for key in ("condition", "filled", "total", "researcher_token", "human_slots"):
            assert key not in body, f"{path} exposes {key}"


async def test_waiting_frame_carries_no_slot_count_and_the_researcher_sees_the_join():
    created = create_session()
    room, token = created["room_code"], created["researcher_token"]
    if researcher_status(room, token).json()["total"] < 2:
        pytest.skip("needs a Condition with at least two Humans, or the join starts the Session")

    ws, frames = await join(room)
    try:
        assert frames[-1] == {"type": "waiting"}
        for frame in frames:
            assert "filled" not in frame and "total" not in frame
        assert researcher_status(room, token).json()["filled"] == 1
    finally:
        await ws.close()


async def test_a_human_is_not_told_when_another_human_joins_or_leaves():
    created = create_session()
    room, token = created["room_code"], created["researcher_token"]
    if researcher_status(room, token).json()["total"] < 3:
        pytest.skip("needs the 3_humans Condition, or the second join starts the Session")

    first, _ = await join(room)
    try:
        second, _ = await join(room)
        assert researcher_status(room, token).json()["filled"] == 2
        await second.close()
        assert await frames_within(first, 1.0) == []
        await asyncio.sleep(0.3)  # the leave is handled after the socket closes
        assert researcher_status(room, token).json()["filled"] == 1
    finally:
        await first.close()
