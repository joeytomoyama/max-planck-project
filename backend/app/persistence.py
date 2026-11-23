"""Persistence: PostgreSQL tables and the async engine.

The schema is created on startup with `create_schema()` (idempotent, no
migrations, no seed script). Table layout follows the spec (issue #9).
Participant `type` is stored here for the Researcher's analysis and must never
be sent to a browser during a Session (Blind Condition).
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

log = logging.getLogger(__name__)

metadata = MetaData()

# `sessions.status` values.
WAITING, ACTIVE, COMPLETED, EXPIRED = "waiting", "active", "completed", "expired"
# `participants.type` values: stored for the Researcher, never sent during a Session.
HUMAN, AI = "human", "ai"

sessions = Table(
    "sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("room_code", String(64), nullable=False, unique=True),
    Column("condition", String(32), nullable=False),
    Column("status", String(16), nullable=False, server_default=WAITING),
    Column("incomplete", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_activity", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("expires_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("decision_maker", String(16)),  # Player Label of the Decision Maker
    Column("decided_by_tiebreak", Boolean),
    # SHA-256 of the Researcher token returned once by `POST /api/sessions`; never sent to a Human.
    Column("researcher_token_hash", String(64)),
    CheckConstraint("status IN ('waiting', 'active', 'completed', 'expired')", name="sessions_status"),
)

participants = Table(
    "participants",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    Column("player_label", String(16), nullable=False),
    Column("type", String(8), nullable=False),
    Column("joined_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_activity", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("dropped_out_at", DateTime(timezone=True)),
    UniqueConstraint("session_id", "player_label"),
    CheckConstraint("type IN ('human', 'ai')", name="participants_type"),
)

rounds = Table(
    "rounds",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    Column("round_number", Integer, nullable=False),
    Column("discussion_start", DateTime(timezone=True)),
    Column("discussion_end", DateTime(timezone=True)),
    Column("voting_end", DateTime(timezone=True)),
    Column("vote_results", JSONB),
    UniqueConstraint("session_id", "round_number"),
)

votes = Table(
    "votes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    Column("round_number", Integer, nullable=False),
    Column("participant_id", Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False),
    Column("target_participant", Integer, ForeignKey("participants.id", ondelete="CASCADE")),
    Column("kind", String(16), nullable=False),
    Column("cast_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("session_id", "round_number", "participant_id"),
    CheckConstraint("kind IN ('vote', 'abstention', 'missing')", name="votes_kind"),
)

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    Column("round_number", Integer, nullable=False),
    Column("phase", String(16), nullable=False, server_default="discussion"),
    Column("participant_id", Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False),
    Column("text", Text, nullable=False),
    Column("sent_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql+asyncpg://mpp:mpp@localhost:5432/mpp")


def create_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or database_url(), pool_pre_ping=True)


# Columns added after the first release, for databases created before them.
_ADDED_COLUMNS = ("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS researcher_token_hash VARCHAR(64)",)


async def create_schema(engine: AsyncEngine, attempts: int = 30, delay: float = 1.0) -> None:
    """Create all tables if missing. Retries while Postgres is still starting up."""
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
                for statement in _ADDED_COLUMNS:  # create_all never alters an existing table
                    await conn.execute(text(statement))
            log.info("Database schema ready")
            return
        except Exception as exc:  # noqa: BLE001 - connection errors vary by driver/startup stage
            if attempt == attempts:
                raise
            log.warning("Database not reachable yet (%s), retrying (%d/%d)", exc, attempt, attempts)
            await asyncio.sleep(delay)


async def ping(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - health check reports, never raises
        log.exception("Database ping failed")
        return False
