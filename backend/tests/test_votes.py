"""Blind voting through the REST interface: the vote is recorded, but no
response ever reveals the target, other participants' choices, or a tally.
"""


def _active_session(db):
    return db.result(
        rows=[{"id": 1, "status": "active", "expires_at": None, "is_expired": False}]
    )


def _participants(db, *ids):
    return db.result(rows=[{"id": pid} for pid in ids])


def _assert_no_vote_inserted(db):
    assert not any(
        c[0] == "EXECUTE" and "INSERT INTO votes" in c[1] for c in db.calls
    )


def test_vote_is_recorded_with_blind_acknowledgement(db, client):
    db.calls.clear()
    db.results.extend([_active_session(db), _participants(db, "Player A", "Player B")])

    response = client.post(
        "/api/sessions/1/votes",
        json={"from_participant": "Player A", "target": "Player B"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "message": "Your vote has been recorded"}
    assert "Player B" not in str(body)
    insert = [c for c in db.calls if c[0] == "EXECUTE" and "INSERT INTO votes" in c[1]]
    assert len(insert) == 1
    assert set(insert[0][2].values()) == {"1", "Player A", "Player B"}
    assert any(call[0] == "COMMIT" for call in db.calls)


def test_vote_on_closed_or_expired_session_is_rejected(db, client):
    for status, is_expired in [("completed", False), ("waiting", False), ("active", True)]:
        db.calls.clear()
        db.results.append(
            db.result(rows=[{"id": 1, "status": status, "is_expired": is_expired}])
        )

        response = client.post(
            "/api/sessions/1/votes",
            json={"from_participant": "Player A", "target": "Player B"},
        )

        assert response.status_code == 409
        _assert_no_vote_inserted(db)


def test_vote_on_unknown_session_is_404(db, client):
    response = client.post(
        "/api/sessions/missing/votes",
        json={"from_participant": "Player A", "target": "Player B"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_participant_cannot_vote_for_themselves(db, client):
    db.calls.clear()
    db.results.append(_active_session(db))

    response = client.post(
        "/api/sessions/1/votes",
        json={"from_participant": "Player A", "target": "Player A"},
    )

    assert response.status_code == 400
    _assert_no_vote_inserted(db)


def test_vote_for_someone_outside_the_session_is_rejected(db, client):
    db.results.extend([_active_session(db), _participants(db, "Player A")])

    response = client.post(
        "/api/sessions/1/votes",
        json={"from_participant": "Player A", "target": "Stranger"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Target is not a participant of this session"


def test_participant_cannot_vote_twice(db, client):
    db.calls.clear()
    db.results.extend(
        [
            _active_session(db),
            _participants(db, "Player A", "Player B"),
            db.result(rows=[{"id": 1}]),
        ]
    )

    response = client.post(
        "/api/sessions/1/votes",
        json={"from_participant": "Player A", "target": "Player B"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Vote already recorded"
    _assert_no_vote_inserted(db)


def test_legacy_singular_vote_route_is_removed(db, client):
    response = client.post(
        "/api/sessions/1/vote",
        json={"from_participant": "Player A", "target": "Player B"},
    )

    # Only the SPA's GET catch-all matches this path, so it returns 405.
    assert response.status_code == 405
