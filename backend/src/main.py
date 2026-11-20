"""
FastAPI backend for Max Planck Project experiment platform.
Handles sessions, WebSocket communication, and REST endpoints.
Uses sync database operations with psycopg2-binary.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime, timedelta
import uuid

app = FastAPI(title="Max Planck Project Backend")

# SQLAlchemy 2.x maps the bare `postgresql://` scheme to psycopg3, but this
# project installs psycopg2-binary, so the driver must be named explicitly.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@db:5432/max_planck_project",
)
engine = create_engine(DATABASE_URL, echo=os.getenv("DEBUG") == "true")
local_session = sessionmaker(engine, expire_on_commit=False)

# Process-global WebSocket registry; guarded by a lock, not thread-local
import threading
active_sessions_lock = threading.Lock()
active_sessions = {}

# index.html lives in backend/static, one level above this module's directory.
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def init_database():
    """Create the schema if it does not exist; never drop live session data."""
    with local_session() as session:
        conn = session.connection()
        _create_schema(conn)
        conn.commit()


def _create_schema(conn):
    """Create all tables used by the experiment."""
    # Create sessions table with oom_code as unique identifier
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            oom_code VARCHAR(64) UNIQUE NOT NULL,
            status VARCHAR(20) DEFAULT 'waiting',
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
    """))
    
    # Create participants table with type enum and last_activity
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS participants (
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            id VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY,  -- e.g., "Player A", "Player B"
            type VARCHAR(10) NOT NULL DEFAULT 'human' CHECK (type IN ('human', 'ai')),
            joined_at TIMESTAMP DEFAULT NOW(),
            last_activity TIMESTAMP DEFAULT NOW()
        )
    """))
    
    # Create rounds table with JSONB vote results
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS rounds (
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            round_number INTEGER NOT NULL,
            discussion_start TIMESTAMP,
            discussion_end TIMESTAMP,
            vote_results JSONB
        )
    """))
    
    # Create votes table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS votes (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            participant_id VARCHAR(20) NOT NULL REFERENCES participants(id),
            target_participant VARCHAR(20) NOT NULL REFERENCES participants(id),
            cast_at TIMESTAMP DEFAULT NOW()
        )
    """))


def create_seed_session(session_id: str = None):
    """Create a demo session with 3 participants for local testing."""
    if session_id is None:
        session_id = uuid.uuid4().hex[:12]

    expires_at = datetime.now() + timedelta(hours=2)

    with local_session() as session:
        conn = session.connection()
        # SQLAlchemy text() uses :name bind parameters, not psycopg2's %s.
        conn.execute(
            text("""
                INSERT INTO sessions (id, oom_code, status, created_at, expires_at)
                VALUES (:id, :oom_code, :status, NOW(), :expires_at)
            """),
            {"id": session_id, "oom_code": f"oom-{session_id}", "status": "waiting", "expires_at": expires_at},
        )

        for pid, ptype in zip(("Player A", "Player B", "Player C"), ("human", "human", "ai")):
            conn.execute(
                text("""
                    INSERT INTO participants (session_id, id, type, joined_at, last_activity)
                    VALUES (:session_id, :id, :type, NOW(), NOW())
                """),
                {"session_id": session_id, "id": pid, "type": ptype},
            )

        conn.commit()
    return session_id


@app.get("/api/sessions")
async def list_sessions(limit: int = 10):
    """List recent sessions."""
    with local_session() as session:
        results = session.execute(
            text("SELECT id, oom_code, status, created_at FROM sessions ORDER BY created_at DESC LIMIT :limit"),
            {"limit": limit}
        )
        return {"sessions": [list(r) for r in results]}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    with local_session() as session:
        result = session.execute(
            text("SELECT s.*, ROUND(EXTRACT(EPOCH FROM (expires_at - NOW()))::NUMERIC, 1) as time_remaining_seconds FROM sessions s WHERE s.id = :id"),
            {"id": session_id}
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        participants_result = session.execute(
            text("SELECT id, joined_at, last_activity FROM participants WHERE session_id = :id ORDER BY id"),
            {"id": session_id}
        )
        participants = [dict(r) for r in participants_result.mappings()]

        return {"session": dict(row), "participants": participants}


@app.get("/api/sessions/{session_id}/start")
async def start_session(session_id: str):
    """Start a waiting session."""
    with local_session() as session:
        session.execute(
            text("UPDATE sessions SET status = 'active' WHERE id = :id"),
            {"id": session_id}
        )
        session.commit()
        return {"status": "active"}


@app.get("/api/sessions/{session_id}/config")
async def get_session_config(session_id: str):
    """Get current config and participants for a session."""
    with local_session() as session:
        result = session.execute(
            text("SELECT s.*, ROUND(EXTRACT(EPOCH FROM (expires_at - NOW()))::NUMERIC, 1) as time_remaining_seconds FROM sessions s WHERE s.id = :id"),
            {"id": session_id}
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        participants_result = session.execute(
            text("SELECT id, joined_at, last_activity FROM participants WHERE session_id = :id ORDER BY id"),
            {"id": session_id}
        )
        participants = [dict(r) for r in participants_result.mappings()]

        return {
            "session": {
                "id": row["id"],
                "oom_code": row["oom_code"],
                "status": row["status"],
                "expires_at": str(row["expires_at"]),
            },
            "time_remaining_seconds": row["time_remaining_seconds"],
            "participants": participants,
        }


@app.post("/api/sessions/{session_id}/participant")
async def add_participant(session_id: str, participant_data: dict):
    """Add a new participant to a session."""
    with local_session() as session:
        # Check session exists and is active
        result = session.execute(text("SELECT id, status FROM sessions WHERE id = :id"), {"id": session_id})
        row = result.mappings().first()
        if not row or row["status"] != "waiting":
            raise HTTPException(status_code=400, detail="Session must be in waiting status to add participants")
        
        participant_id = participant_data.get("id")
        participant_type = participant_data.get("type", "human")
        
        session.execute(text("""
            INSERT INTO participants (session_id, id, type, joined_at, last_activity) 
            VALUES (:session_id, :id, :type, NOW(), NOW())
        """), {"session_id": session_id, "id": participant_id, "type": participant_type})
        
        session.commit()
        return {"status": "ok", "participant_id": participant_id}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(session_id: str, websocket: WebSocket):
    """WebSocket endpoint for real-time chat and voting."""
    await websocket.accept()
    
    # Check session exists and is active
    with local_session() as session:
        result = session.execute(text("SELECT id, status FROM sessions WHERE id = :id"), {"id": session_id})
        row = result.mappings().first()
        if not row or row["status"] != "active":
            await websocket.close(code=4001)  # Session expired or not active
            return

        with active_sessions_lock:
            participant_id = f"Player {len(active_sessions.get(session_id, [])) + 1}"

        with local_session() as participant_session:
            participant_session.execute(
                text("""
                    INSERT INTO participants (session_id, id, type, joined_at, last_activity)
                    VALUES (:session_id, :id, 'human', NOW(), NOW())
                """),
                {"session_id": session_id, "id": participant_id},
            )
            participant_session.commit()

            with active_sessions_lock:
                active_sessions.setdefault(session_id, []).append(websocket)

    try:
        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_text("pong")
            elif data.startswith("chat:") or data.startswith("vote:"):
                message_content = data[5:]  # Drop the "chat:"/"vote:" prefix
                await broadcast(f"{session_id}: {message_content}")
    except WebSocketDisconnect:
        with active_sessions_lock:
            if websocket in active_sessions.get(session_id, []):
                active_sessions[session_id].remove(websocket)

        with local_session() as session:
            session.execute(
                text("DELETE FROM participants WHERE session_id = :session_id AND id = :participant_id"),
                {"session_id": session_id, "participant_id": participant_id},
            )
            session.commit()


def session_id_from_message(message: str):
    """Return the session-id prefix of a broadcast message, or None if absent."""
    if ":" not in message:
        return None
    session_id = message.split(":", 1)[0].strip()
    return session_id or None


async def broadcast(message: str):
    """Broadcast a message to all clients connected to the given session."""
    session_id = session_id_from_message(message)
    if session_id is None:
        return

    # Snapshot the sockets under the lock; never hold it across an await.
    with active_sessions_lock:
        sockets = list(active_sessions.get(session_id, ()))

    for websocket in sockets:
        try:
            await websocket.send_text(message)
        except Exception:
            continue


@app.post("/api/sessions/{session_id}/vote")
async def cast_vote(session_id: str, vote_data: dict):
    """Cast a vote from a participant."""
    with local_session() as session:
        # Get participant's current activities to update last_activity
        result = session.execute(
            text("SELECT id FROM participants WHERE session_id = :id AND id = :participant_id"),
            {"id": session_id, "participant_id": vote_data["from_participant"]}
        )
        participant = result.scalar_one_or_none()
        
        if not participant:
            raise HTTPException(status_code=404, detail="Participant not found")
        
        # Update last_activity
        session.execute(text("""
            UPDATE participants SET last_activity = NOW() 
            WHERE id = :participant_id
        """), {"participant_id": vote_data["from_participant"]})
        
        # Insert vote
        session.execute(text("""
            INSERT INTO votes (session_id, participant_id, target_participant, cast_at) 
            VALUES (:session_id, :from_participant, :to_participant, NOW())
        """), {
            "session_id": session_id,
            "from_participant": vote_data["from_participant"],
            "to_participant": vote_data["target"]
        })
        
        session.commit()
        return {"status": "ok"}


@app.on_event("startup")
async def on_startup():
    """Initialize database tables on startup."""
    init_database()


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """Serve the SPA for non-API paths; API misses stay JSON 404s."""
    if full_path.split("/", 1)[0] in {"api", "ws"}:
        raise HTTPException(status_code=404, detail="Not Found")

    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return HTMLResponse('<!doctype html><html><body><div id="root"></div></body></html>')


# Seed data initialization (create demo session if requested)
if os.getenv("CREATE_SEED") == "true":
    create_seed_session()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
