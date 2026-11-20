"""Test scaffolding: replaces the database boundary with in-memory fakes."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main  # noqa: E402


class FakeMappings:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class FakeResult:
    """Minimal stand-in for a SQLAlchemy Result."""

    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def __iter__(self):
        return iter(self._rows)

    def scalar_one_or_none(self):
        # SQLAlchemy scalar access returns the first column, not the whole row.
        if self._scalar is not None:
            return self._scalar
        if not self._rows:
            return None
        first = self._rows[0]
        return first[0] if isinstance(first, (tuple, list)) else first

    def scalar_one(self):
        return self.scalar_one_or_none()

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return FakeMappings(self._rows)

    def all(self):
        return self._rows


class FakeConnection:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, statement, params=None):
        self.calls.append(("EXECUTE", str(statement), params))
        return FakeResult()

    def commit(self):
        self.calls.append(("COMMIT", None, None))


@pytest.fixture
def db(monkeypatch):
    results = []
    calls = []

    class FakeSession:
        def execute(self, statement, params=None):
            calls.append(("EXECUTE", str(statement), params))
            return results.pop(0) if results else FakeResult()

        def commit(self):
            calls.append(("COMMIT", None, None))

        def connection(self):
            return FakeConnection(calls)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake = FakeSession()
    monkeypatch.setattr(main, "local_session", lambda: fake)
    monkeypatch.setattr(main, "engine", MagicMock())
    monkeypatch.setattr(main, "active_sessions", {})
    return SimpleNamespace(results=results, calls=calls, session=fake, result=FakeResult)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: requires a live PostgreSQL instance"
    )


def pytest_collection_modifyitems(items):
    """DB-schema tests need a live PostgreSQL; opt in explicitly."""
    if os.getenv("RUN_DB_INTEGRATION_TESTS") == "true":
        return
    skip = pytest.mark.skip(
        reason="requires a live PostgreSQL instance (set RUN_DB_INTEGRATION_TESTS=true)"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    with TestClient(main.app) as test_client:
        yield test_client
