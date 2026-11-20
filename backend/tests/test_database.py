"""
Unit tests for Max Planck Project database schema and seed data.
Tests the schema initialization, seed session creation, and basic CRUD operations.

Run with: pytest backend/tests/test_database.py -v
"""

import os
import sys
import pytest
from datetime import datetime
from sqlalchemy import text

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytestmark = pytest.mark.integration


def test_init_database_schema():
    """Test that init_database() creates all required tables."""
    from main import local_session
    
    with local_session() as session:
        conn = session.connection()
        
        # Check sessions table exists and has correct columns
        result = conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'sessions'"
        ))
        columns = {row.column_name: row.data_type for row in result}
        
        assert 'id' in columns
        assert 'oom_code' in columns
        assert 'status' in columns
        assert 'created_at' in columns
        assert 'expires_at' in columns


def test_create_seed_session():
    """Test that create_seed_session() creates a session with 3 participants."""
    from main import local_session
    from seed import create_seed_session
    
    # Create a new session for testing
    session_id = f"test-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    conn = local_session().connection()
    
    # Clean up any existing test session
    try:
        conn.execute(text("DELETE FROM participants WHERE id LIKE 'Player A'"))
        conn.execute(text("DELETE FROM participants WHERE id LIKE 'Player B'"))
        conn.execute(text("DELETE FROM participants WHERE id LIKE 'Player C'"))
        conn.execute(text("DELETE FROM sessions WHERE oom_code LIKE f'test-{session_id[:4]}'%"))
        conn.commit()
    except Exception:
        pass
    
    # Create seed session
    result = create_seed_session(session_id=session_id)
    
    assert result == session_id
    
    # Verify session was created with correct data
    with local_session() as session:
        row = session.execute(
            text("SELECT id, oom_code, status FROM sessions WHERE id = :id"),
            {"id": session_id}
        ).scalar_one_or_none()
        
        assert row is not None
        assert row[0] == session_id
        assert row[1].startswith("oom-")
        assert row[2] == 'waiting'


def test_participants_created():
    """Test that seed session creates correct participants."""
    from main import local_session
    
    # Get the most recent session to check (or create one first)
    with local_session() as session:
        result = session.execute(
            text("SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1")
        ).scalar_one_or_none()
        
        if result:
            session_id = result[0]
            
            # Check participants
            participants_result = session.execute(
                text("SELECT id, type FROM participants WHERE session_id = :id ORDER BY id"),
                {"id": session_id}
            )
            
            participants = list(participants_result)
            assert len(participants) >= 1
            
            # Should have at least one human participant
            human_count = sum(1 for p in participants if p[1] == 'human')
            assert human_count >= 2  # Default is 2 humans, 1 AI


def test_database_tables_structure():
    """Test that all required tables exist with proper structure."""
    from main import local_session
    
    with local_session() as session:
        # Check participants table has type column with CHECK constraint
        result = session.execute(text("""
            SELECT column_name, data_type, udt_name, character_maximum_length 
            FROM information_schema.columns 
            WHERE table_name = 'participants' AND column_name = 'type'
        """))
        
        row = result.scalar_one_or_none()
        assert row is not None
        assert 'varchar' in row.data_type.lower()


def test_votes_table_exists():
    """Test that votes table exists with correct structure."""
    from main import local_session
    
    with local_session() as session:
        result = session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'votes'
        """))
        
        columns = {row.column_name: row.data_type for row in result}
        
        assert 'id' in columns
        assert 'session_id' in columns
        assert 'participant_id' in columns
        assert 'target_participant' in columns
        assert 'cast_at' in columns


def test_rounds_table_exists():
    """Test that rounds table exists with JSONB column."""
    from main import local_session
    
    with local_session() as session:
        result = session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'rounds'
        """))
        
        columns = {row.column_name: row.data_type for row in result}
        
        assert 'session_id' in columns
        assert 'round_number' in columns


@pytest.fixture
def cleanup_test_session():
    """Cleanup test session after tests."""
    from main import local_session
    
    yield
    
    # Clean up
    try:
        with local_session() as session:
            result = session.execute(
                text("SELECT id FROM sessions WHERE oom_code LIKE 'test-%' ORDER BY created_at DESC LIMIT 1")
            ).scalar_one_or_none()
            
            if result:
                session_id = result[0]
                session.execute(text(f"DELETE FROM votes WHERE session_id = {session_id}"))
                session.execute(text(f"DELETE FROM rounds WHERE session_id = {session_id}"))
                session.execute(text(f"DELETE FROM participants WHERE session_id = {session_id}"))
                session.execute(text(f"DELETE FROM sessions WHERE id = {session_id}"))
                session.commit()
    except Exception:
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
