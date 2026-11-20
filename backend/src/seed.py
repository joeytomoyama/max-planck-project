"""
Seed data script for Max Planck Project.
Creates a demo session with 3 participants for local testing.

Usage:
    python seed.py              # Creates seed session in connected database
    python seed.py --help       # Show help and options
"""

import sys
import os
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))


def create_seed_session(db_url: str = None):
    """
    Create a demo session with 3 participants (2 human, 1 AI) for local testing.
    
    Args:
        db_url: PostgreSQL connection URL (defaults to env var or hardcoded value)
    
    Returns:
        Session ID of the created session
    """
    if not db_url:
        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:secretpgpass@db:5432/max_planck_project")
    
    conn = None
    try:
        from psycopg2 import connect, OperationalError
        
        # Connect to database
        conn = connect(db_url)
        
        with conn:
            # Generate session ID and expires_at
            session_id = f"seed-{uuid.uuid4().hex[:8]}"
            expires_at = datetime.now() + timedelta(hours=2)
            
            # Create the session
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (id, oom_code, status, created_at, expires_at) 
                VALUES (%s, %s, %s, NOW(), %s)
            """, (session_id, f"oom-{session_id}", 'waiting', expires_at))
            
            conn.commit()
            
            # Create 3 participants (2 human, 1 AI by default)
            participant_data = [
                ("Player A", "human"),
                ("Player B", "human"),
                ("Player C", "ai"),
            ]
            
            for pid, ptype in participant_data:
                cursor.execute("""
                    INSERT INTO participants (session_id, id, type, joined_at, last_activity) 
                    VALUES (%s, %s, %s, NOW(), NOW())
                """, (session_id, pid, ptype))
            
            conn.commit()
            
            # Print success message with session details
            print(f"\n✓ Seed session created successfully!")
            print(f"  Session ID: {session_id}")
            print(f"  OOM Code:    oom-{session_id}")
            print(f"  Expires at:  {expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"\nParticipants:")
            
            cursor.execute("""
                SELECT id, type FROM participants 
                WHERE session_id = %s ORDER BY id
            """, (session_id,))
            
            participants = cursor.fetchall()
            for p in participants:
                icon = "🤖" if p[1] == 'ai' else "👤"
                print(f"    {icon} {p[0]} ({p[1]})")
            
            print(f"\nWebSocket endpoint: ws://localhost:8000/ws/{session_id}")
            print(f"\nTo connect to this session, visit:")
            print(f"  http://localhost:3000/{session_id}")
            print("\n---")
            print("This demo session is ready for testing!")
            print("You can join with the WebSocket at /ws/:sessionId")
            
    except OperationalError as e:
        print(f"\n✗ Database connection failed: {e}")
        print(f"   Make sure PostgreSQL is running and accessible.")
        print(f"   Check DATABASE_URL environment variable.")
    except Exception as e:
        print(f"\n✗ Error creating seed session: {e}")
    
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Create seed demo session")
    parser.add_argument("--db", type=str, help="PostgreSQL connection URL (optional)")
    args = parser.parse_args()
    
    create_seed_session(db_url=args.db)
