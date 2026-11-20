"""Real-time channel: session gating and peer broadcast."""

import pytest
from fastapi import WebSocketDisconnect


def test_chat_message_is_broadcast_to_peer(db, client):
    # Each connection checks the session, then inserts a participant row.
    for _ in range(2):
        db.results.append(db.result(rows=[{"id": 1, "status": "active"}]))
        db.results.append(db.result())

    with client.websocket_connect("/ws/oom-1") as sender:
        with client.websocket_connect("/ws/oom-1") as peer:
            sender.send_text("chat:hello")
            assert peer.receive_text() == "oom-1: hello"


def test_waiting_session_rejects_websocket(db, client):
    db.results.append(db.result(rows=[{"id": 1, "status": "waiting"}]))

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/oom-1") as websocket:
            websocket.receive_text()

    assert exc.value.code == 4001
