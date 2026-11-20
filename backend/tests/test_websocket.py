"""Real-time channel: session gating, chat broadcast, blind vote events.

Frames are JSON: clients send {"type": "chat", "text": ...} or
{"type": "vote", "target": ...}; the server sends JSON event frames back.
"""

import json

import pytest
from fastapi import WebSocketDisconnect


def _state(db, status="active", is_expired=False):
    return db.result(
        rows=[
            {
                "id": 1,
                "status": status,
                "expires_at": None,
                "is_expired": is_expired,
            }
        ]
    )


def _connect_two_clients(db):
    # Each connection checks the session, then inserts a participant row.
    for _ in range(2):
        db.results.append(_state(db))
        db.results.append(db.result())


def _frame(text):
    return json.loads(text)


def test_chat_message_is_broadcast_to_peer(db, client):
    _connect_two_clients(db)
    db.results.append(_state(db))  # chat re-checks that the session is still open

    with client.websocket_connect("/ws/1") as sender:
        with client.websocket_connect("/ws/1") as peer:
            sender.send_text(json.dumps({"type": "chat", "text": "hello"}))
            assert _frame(peer.receive_text()) == {"type": "chat", "text": "hello"}


def test_vote_event_acknowledges_voter_and_notifies_peers_blindly(db, client):
    _connect_two_clients(db)
    # Recording a vote: session state, participant membership, duplicate check.
    db.results.extend(
        [
            _state(db),
            db.result(rows=[{"id": "Player 1"}, {"id": "Player 2"}]),
            db.result(),
        ]
    )

    with client.websocket_connect("/ws/1") as sender:
        with client.websocket_connect("/ws/1") as peer:
            sender.send_text(json.dumps({"type": "vote", "target": "Player 2"}))
            ack = _frame(sender.receive_text())
            notice = _frame(peer.receive_text())

    assert ack == {"type": "vote_ack", "message": "Your vote has been recorded"}
    assert notice == {"type": "vote_notice", "message": "A vote was cast"}
    assert "Player 2" not in json.dumps(ack)
    assert "Player 2" not in json.dumps(notice)


def test_invalid_vote_sends_error_to_voter(db, client):
    _connect_two_clients(db)
    db.results.extend(
        [
            _state(db),
            db.result(rows=[{"id": "Player 1"}]),
        ]
    )

    with client.websocket_connect("/ws/1") as sender:
        with client.websocket_connect("/ws/1"):
            sender.send_text(json.dumps({"type": "vote", "target": "Stranger"}))
            assert _frame(sender.receive_text()) == {
                "type": "error",
                "message": "Target is not a participant of this session",
            }


def test_chat_on_closed_session_is_rejected(db, client):
    db.results.append(_state(db))
    db.results.append(db.result())
    db.results.append(_state(db, status="completed"))

    with client.websocket_connect("/ws/1") as websocket:
        websocket.send_text(json.dumps({"type": "chat", "text": "hello"}))
        assert _frame(websocket.receive_text()) == {
            "type": "error",
            "message": "Session is closed",
        }


def test_malformed_frame_is_rejected(db, client):
    db.results.append(_state(db))
    db.results.append(db.result())

    with client.websocket_connect("/ws/1") as websocket:
        websocket.send_text("not json")
        assert _frame(websocket.receive_text()) == {
            "type": "error",
            "message": "Invalid message format",
        }


def test_ping_returns_pong(db, client):
    db.results.append(_state(db))
    db.results.append(db.result())

    with client.websocket_connect("/ws/1") as websocket:
        websocket.send_text(json.dumps({"type": "ping"}))
        assert _frame(websocket.receive_text()) == {"type": "pong"}


def test_waiting_session_rejects_websocket(db, client):
    db.results.append(_state(db, status="waiting"))

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/1") as websocket:
            websocket.receive_text()

    assert exc.value.code == 4001


def test_expired_session_rejects_websocket(db, client):
    db.results.append(_state(db, is_expired=True))

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/1") as websocket:
            websocket.receive_text()

    assert exc.value.code == 4001
