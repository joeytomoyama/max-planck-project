"""Public HTTP surface of the backend: boot, routing, response shapes, writes."""

import main  # noqa: E402


def test_create_session_generates_a_random_room_code(db, client, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(main.uuid, "uuid4", lambda: SimpleNamespace(hex="abcd1234efgh5678"))
    db.calls.clear()
    db.results.append(
        db.result(
            rows=[
                {
                    "id": 7,
                    "oom_code": "oom-abcd1234efgh",
                    "status": "waiting",
                    "created_at": None,
                    "expires_at": None,
                }
            ]
        )
    )

    response = client.post("/api/sessions")

    assert response.status_code == 201
    session = response.json()["session"]
    assert session["id"] == 7
    assert session["oom_code"] == "oom-abcd1234efgh"
    assert session["status"] == "waiting"
    insert = [c for c in db.calls if c[0] == "EXECUTE" and "INSERT INTO sessions" in c[1]]
    assert insert and insert[0][2]["oom_code"] == "oom-abcd1234efgh"
    assert 15 in insert[0][2].values()


def test_app_starts_and_lists_sessions(db, client):
    db.results.append(db.result(rows=[(1, "oom-1", "waiting", None)]))
    response = client.get("/api/sessions")
    assert response.status_code == 200
    assert response.json()["sessions"] == [[1, "oom-1", "waiting", None]]


def test_get_session_returns_session_mapping_and_participants(db, client):
    db.results.append(
        db.result(
            rows=[
                {
                    "id": 1,
                    "oom_code": "oom-1",
                    "status": "waiting",
                    "expires_at": None,
                    "time_remaining_seconds": 900.0,
                }
            ]
        )
    )
    db.results.append(
        db.result(
            rows=[{"id": "Player A", "joined_at": None, "last_activity": None}]
        )
    )
    db.results.append(db.result(rows=[(2,)]))  # current round from rounds table

    response = client.get("/api/sessions/1")

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["oom_code"] == "oom-1"
    assert body["session"]["time_remaining_seconds"] == 900.0
    assert body["participants"] == [
        {"id": "Player A", "joined_at": None, "last_activity": None}
    ]
    assert body["current_round"] == 2
    assert "type" not in body["participants"][0]


def test_start_session_transitions_waiting_session_to_active(db, client):
    db.calls.clear()
    db.results.append(
        db.result(rows=[{"id": 1, "status": "waiting", "is_expired": False}])
    )

    response = client.post("/api/sessions/1/start")

    assert response.status_code == 200
    assert response.json() == {"status": "active"}
    updates = [
        c for c in db.calls
        if c[0] == "EXECUTE" and "UPDATE sessions SET status = 'active'" in c[1]
    ]
    assert len(updates) == 1
    assert any(call[0] == "COMMIT" for call in db.calls)


def test_start_session_rejects_closed_or_expired_sessions(db, client):
    for status, is_expired in [("active", False), ("completed", False), ("waiting", True)]:
        db.calls.clear()
        db.results.append(
            db.result(rows=[{"id": 1, "status": status, "is_expired": is_expired}])
        )

        response = client.post("/api/sessions/1/start")

        assert response.status_code == 409
        assert not any(
            c[0] == "EXECUTE" and "UPDATE sessions SET status" in c[1]
            for c in db.calls
        )


def test_start_session_reports_unknown_session(db, client):
    response = client.post("/api/sessions/missing/start")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_legacy_get_start_route_is_removed(db, client):
    # The catch-all SPA route turns unmatched API paths into a JSON 404.
    response = client.get("/api/sessions/1/start")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_unknown_non_api_path_serves_the_spa(db, client):
    response = client.get("/waiting")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
