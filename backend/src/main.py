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
            text("SELECT id, room_code, status, created_at FROM sessions ORDER BY created_at DESC LIMIT :limit"),
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
            text("SELECT id, name, type, joined_at FROM participants WHERE session_id = :id ORDER BY id"),
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
            text("SELECT id, name, type, joined_at FROM participants WHERE session_id = :id ORDER BY id"),
            {"id": session_id}
        )
        participants = [list(r) for r in participants_result]
        
        return {
            "session": {
                "id": row[0],
                "room_code": row[1],
                "status": row[2],
                "expires_at": str(row[3])
            },
            "time_remaining": row[4],
            "participants": participants
        }


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(session_id: str, websocket: WebSocket):
    """WebSocket endpoint for real-time chat and voting."""
    await websocket.accept()
    
    # Check session exists and is active
    with local_session() as session:
        result = session.execute(text("SELECT id FROM sessions WHERE id = :id"), {"id": session_id})
        if not result.scalar_one():
            await websocket.close(code=4001)  # Session expired
            return
        
        with local_session() as participant_session:
            participant_session.execute(
                text("INSERT INTO participants (session_id, name, type, joined_at) VALUES (:session_id, :name, :type, NOW())"),
                {"session_id": session_id, "name": f"Player {len(active_sessions.get(session_id, [])) + 1}", "type": "human"}
            )
            
            with active_sessions_lock:
                if session_id not in active_sessions:
                    active_sessions[session_id] = []
                active_sessions[session_id].append(websocket)
    
    try:
        while True:
            data = websocket.receive_text()
            
            if data == "ping":
                await websocket.send_text("pong")
            else:
                # Handle chat message
                message = data.strip("'\"")  # Remove WebSocket quotes
                broadcast(f"{session_id}: {message}")
    except WebSocketDisconnect:
        with local_session() as session:
            session.execute(
                text("DELETE FROM participants WHERE session_id = :id AND name IN (SELECT p.name FROM participants p WHERE p.session_id = :sid)"),
                {"id": session_id, "sid": session_id}
            )


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


@app.post("/api/rooms/{room_code}")
async def create_room(room_code: str):
    """Create a new experiment room."""
    with local_session() as session:
        result = session.execute(
            text("SELECT id FROM rooms WHERE room_code = :code"),
            {"code": room_code}
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Room code already taken")
        
        expires_at = datetime.now() + timedelta(minutes=15)
        return session.execute(
            text("INSERT INTO rooms (room_code, created_at, expires_at) VALUES (:room_code, NOW(), :expires_at) RETURNING id"),
            {"room_code": room_code, "expires_at": expires_at}
        ).scalar_one()


def create_tables(conn):
    """Create database tables."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            room_code VARCHAR(64) UNIQUE NOT NULL,
            status VARCHAR(20) DEFAULT 'waiting',
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
    """))
    
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS participants (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            name VARCHAR(100),
            type VARCHAR(20) DEFAULT 'human',
            joined_at TIMESTAMP DEFAULT NOW()
        )
    """))
    
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS rooms (
            id SERIAL PRIMARY KEY,
            room_code VARCHAR(64) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
    """))
    
    conn.commit()


@app.on_event("startup")
async def on_startup():
    """Initialize database tables on startup."""
    with local_session() as session:
        create_tables(conn=session.connection())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
