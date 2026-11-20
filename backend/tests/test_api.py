"""Public HTTP surface of the backend: boot, routing, response shapes, writes."""


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

    response = client.get("/api/sessions/1")

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["oom_code"] == "oom-1"
    assert body["session"]["time_remaining_seconds"] == 900.0
    assert body["participants"] == [
        {"id": "Player A", "joined_at": None, "last_activity": None}
    ]
    assert "type" not in body["participants"][0]


def test_start_session_commits_the_status_change(db, client):
    response = client.get("/api/sessions/1/start")
    assert response.status_code == 200
    assert any("UPDATE sessions SET status" in call[1] for call in db.calls if call[0] == "EXECUTE")
    assert any(call[0] == "COMMIT" for call in db.calls)


def test_unknown_non_api_path_serves_the_spa(db, client):
    response = client.get("/waiting")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
