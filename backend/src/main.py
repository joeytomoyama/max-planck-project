"""
FastAPI backend for Max Planck Project experiment platform.
Handles sessions, WebSocket communication, and REST endpoints.
Uses sync database operations with psycopg2-binary.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import create_engine, text, Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import declarative_base, Session, sessionmaker
import os
from datetime import datetime, timedelta
import uuid

app = FastAPI(title="Max Planck Project Backend")

# Database setup - using sync psycopg2-binary which works with PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:secretpgpass@db:5432/max_planck_project")

from sqlalchemy import create_engine
engine = create_engine(DATABASE_URL, echo=os.getenv("DEBUG") == "true")
local_session = sessionmaker(engine, expire_on_commit=False)

# Create a thread-local storage for active WebSocket connections
import threading
active_sessions_lock = threading.Lock()
active_sessions = {}

# Initialize static files directory for React build
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)


def init_database():
    """Initialize database with proper schema and seed data."""
    from psycopg2 import sql
    
    conn = local_session().connection()
    
    # Drop existing tables if they exist (for clean initialization)
    conn.execute(text("DROP TABLE IF EXISTS rooms CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS votes CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS rounds CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS participants CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS sessions CASCADE"))
    conn.commit()
    
    # Create sessions table with oom_code as unique identifier
    conn.execute(text("""
        CREATE TABLE sessions (
            id SERIAL PRIMARY KEY,
            oom_code VARCHAR(64) UNIQUE NOT NULL,
            status VARCHAR(20) DEFAULT 'waiting',
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
    """))
    
    # Create participants table with type enum and last_activity
    conn.execute(text("""
        CREATE TABLE participants (
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            id VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY,  -- e.g., "Player A", "Player B"
            type VARCHAR(10) NOT NULL DEFAULT 'human' CHECK (type IN ('human', 'ai')),
            joined_at TIMESTAMP DEFAULT NOW(),
            last_activity TIMESTAMP DEFAULT NOW()
        )
    """))
    
    # Create rounds table with JSONB vote results
    conn.execute(text("""
        CREATE TABLE rounds (
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            round_number INTEGER NOT NULL,
            discussion_start TIMESTAMP,
            discussion_end TIMESTAMP,
            vote_results JSONB
        )
    """))
    
    # Create votes table
    conn.execute(text("""
        CREATE TABLE votes (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            participant_id VARCHAR(20) NOT NULL REFERENCES participants(id),
            target_participant VARCHAR(20) NOT NULL REFERENCES participants(id),
            cast_at TIMESTAMP DEFAULT NOW()
        )
    """))
    
    conn.commit()


def create_seed_session(session_id: int = None):
    """Create a demo session with 3 participants for local testing."""
    from psycopg2 import sql
    
    conn = local_session().connection()
    
    # Generate or use provided session ID
    if session_id is None:
        session_id = uuid.uuid4().hex[:12]
    
    expires_at = datetime.now() + timedelta(hours=2)
    
    # Insert seed session
    conn.execute(text("""
        INSERT INTO sessions (id, oom_code, status, created_at, expires_at) 
        VALUES (%s, %s, %s, NOW(), %s)
    """), (session_id, f"oom-{session_id}", 'waiting', expires_at))
    
    # Insert 3 participants (2 human, 1 AI)
    participant_ids = ["Player A", "Player B", "Player C"]
    participant_types = ["human", "human", "ai"]
    
    for pid, ptype in zip(participant_ids, participant_types):
        conn.execute(text("""
            INSERT INTO participants (session_id, id, type, joined_at, last_activity) 
            VALUES (%s, %s, %s, NOW(), NOW())
        """), (session_id, pid, ptype))
    
    conn.commit()
    return session_id


@app.get("/*", include_in_schema=False)
async def serve_frontend(request: Request):
    """Serve React frontend app with API routes accessible via /api/ prefix."""
    if request.scope['method'] == 'GET' and 'index.html' not in STATIC_DIR:
        # Serve index.html for all non-API paths
        try:
            return FileResponse(os.path.join(STATIC_DIR, "index.html"))
        except FileNotFoundError:
            from fastapi.responses import HTMLResponse
            return HTMLResponse("<html><head><title>SPA App</title></head><body>Loading...</body></html>")
    # For API routes, let them pass through
    raise HTTPException(status_code=404, detail="Not Found")


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
            text("SELECT s.*, ROUND(EXTRACT(EPOCH FROM (expires_at - NOW()))::NUMERIC, 1) as time_remaining FROM sessions s WHERE s.id = :id"),
            {"id": session_id}
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        
        participants_result = session.execute(
            text("SELECT id, type, joined_at, last_activity FROM participants WHERE session_id = :id ORDER BY id"),
            {"id": session_id}
        )
        participants = [list(r) for r in participants_result]
        
        return {"session": dict(row), "participants": participants}


@app.get("/api/sessions/{session_id}/start")
async def start_session(session_id: str):
    """Start a waiting session."""
    with local_session() as session:
        session.execute(
            text("UPDATE sessions SET status = 'active' WHERE id = :id"),
            {"id": session_id}
        )
        return {"status": "active"}


@app.get("/api/sessions/{session_id}/config")
async def get_session_config(session_id: str):
    """Get current config and participants for a session."""
    with local_session() as session:
        result = session.execute(
            text("SELECT s.*, ROUND(EXTRACT(EPOCH FROM (expires_at - NOW()))::NUMERIC, 1) as time_remaining FROM sessions s WHERE s.id = :id"),
            {"id": session_id}
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        
        participants_result = session.execute(
            text("SELECT id, type, joined_at, last_activity FROM participants WHERE session_id = :id ORDER BY id"),
            {"id": session_id}
        )
        participants = [list(r) for r in participants_result]
        
        return {
            "session": {
                "id": row[0],
                "oom_code": row[1],
                "status": row[2],
                "expires_at": str(row[3])
            },
            "time_remaining": row[4],
            "participants": participants
        }


@app.post("/api/sessions/{session_id}/participant")
async def add_participant(session_id: str, participant_data: dict):
    """Add a new participant to a session."""
    with local_session() as session:
        # Check session exists and is active
        result = session.execute(text("SELECT id, status FROM sessions WHERE id = :id"), {"id": session_id})
        row = result.scalar_one_or_none()
        if not row or row[1] != 'waiting':
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
        row = result.scalar_one_or_none()
        if not row or row[1] != 'active':
            await websocket.close(code=4001)  # Session expired or not active
            return
        
        participant_id = f"Player {len(active_sessions.get(session_id, [])) + 1}"
        
        with local_session() as participant_session:
            participant_session.execute(text("""
                INSERT INTO participants (session_id, id, type, joined_at, last_activity) 
                VALUES (:session_id, :id, 'human', NOW(), NOW())
            """), {"session_id": session_id, "id": participant_id})
            
            with active_sessions_lock:
                if session_id not in active_sessions:
                    active_sessions[session_id] = []
                active_sessions[session_id].append(websocket)
    
    try:
        while True:
            data = websocket.receive_text()
            
            if data == "ping":
                await websocket.send_text("pong")
            elif data.startswith("chat:") or data.startswith("vote:"):
                # Handle chat message or voting
                message_content = data[5:]  # Remove "chat:" or "vote:" prefix
                broadcast(f"{session_id}: {message_content}")
    except WebSocketDisconnect:
        with local_session() as session:
            session.execute(text("""
                DELETE FROM participants WHERE session_id = :id AND id IN (
                    SELECT p.id FROM participants p WHERE p.session_id = :sid
                )
            """), {"id": session_id, "sid": session_id})


async def broadcast(message: str):
    """Broadcast message to all connected clients in a session."""
    with active_sessions_lock:
        if ":" in message:
            try:
                session_key = int(message.split(":")[0])
            except ValueError:
                return
        
        if session_key is not None and session_key in active_sessions:
            for websocket in active_sessions[session_key]:
                try:
                    await websocket.send_text(message)
                except Exception:
                    break


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


def create_tables(conn):
    """Legacy function - removed in favor of init_database()."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            oom_code VARCHAR(64) UNIQUE NOT NULL,
            status VARCHAR(20) DEFAULT 'waiting',
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
    """))
    
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS participants (
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            id VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY,
            type VARCHAR(10) NOT NULL DEFAULT 'human' CHECK (type IN ('human', 'ai')),
            joined_at TIMESTAMP DEFAULT NOW(),
            last_activity TIMESTAMP DEFAULT NOW()
        )
    """))
    
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS rounds (
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            round_number INTEGER NOT NULL,
            discussion_start TIMESTAMP,
            discussion_end TIMESTAMP,
            vote_results JSONB
        )
    """))
    
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS votes (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            participant_id VARCHAR(20) NOT NULL REFERENCES participants(id),
            target_participant VARCHAR(20) NOT NULL REFERENCES participants(id),
            cast_at TIMESTAMP DEFAULT NOW()
        )
    """))
    
    conn.commit()


@app.on_event("startup")
async def on_startup():
    """Initialize database tables on startup."""
    with local_session() as session:
        init_database(session.connection())


# Seed data initialization (create demo session if requested)
if os.getenv("CREATE_SEED") == "true":
    create_seed_session()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
