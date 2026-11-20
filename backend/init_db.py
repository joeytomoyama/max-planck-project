"""
Database initialization script for Max Planck Project.
Runs migrations and optionally creates seed data.

Usage:
    python init_db.py --seed           # Create tables and seed demo session
    python init_db.py --help          # Show help
"""

import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))


def initialize_database(create_seed: bool = False):
    """
    Initialize database schema and optionally create seed data.
    
    Args:
        create_seed: Whether to create a demo session with participants
    """
    from psycopg2 import connect, OperationalError
    
    # psycopg2.connect() needs a libpq DSN/URI, not SQLAlchemy's +driver scheme.
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/max_planck_project")
    
    conn = None
    try:
        print(f"Connecting to database: {db_url}")
        
        # Connect to database
        conn = connect(db_url)
        cursor = conn.cursor()
        
        print("Initializing database schema...")
        
        # Drop existing tables (idempotent for clean migrations)
        for table in ['votes', 'rounds', 'participants', 'sessions']:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            print(f"  ✓ Dropped {table} table")
        
        # Create sessions table
        cursor.execute("""
            CREATE TABLE sessions (
                id SERIAL PRIMARY KEY,
                oom_code VARCHAR(64) UNIQUE NOT NULL,
                status VARCHAR(20) DEFAULT 'waiting',
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP
            )
        """)
        print("  ✓ Created sessions table")
        
        # Create participants table
        cursor.execute("""
            CREATE TABLE participants (
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                id VARCHAR(20) UNIQUE NOT NULL PRIMARY KEY,
                type VARCHAR(10) NOT NULL DEFAULT 'human',
                joined_at TIMESTAMP DEFAULT NOW(),
                last_activity TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Add CHECK constraint for type enum
        cursor.execute("""
            ALTER TABLE participants 
            ADD CONSTRAINT participants_type_check 
            CHECK (type IN ('human', 'ai'))
        """)
        print("  ✓ Created participants table with CHECK constraint")
        
        # Create rounds table
        cursor.execute("""
            CREATE TABLE rounds (
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                round_number INTEGER NOT NULL,
                discussion_start TIMESTAMP,
                discussion_end TIMESTAMP,
                vote_results JSONB
            )
        """)
        print("  ✓ Created rounds table with JSONB column")
        
        # Create votes table
        cursor.execute("""
            CREATE TABLE votes (
                id SERIAL PRIMARY KEY,
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                participant_id VARCHAR(20) NOT NULL,
                target_participant VARCHAR(20) NOT NULL,
                cast_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("  ✓ Created votes table")
        
        # Create indexes for performance
        cursor.execute("CREATE INDEX idx_sessions_oom_code ON sessions(oom_code)")
        cursor.execute("CREATE INDEX idx_participants_session_id ON participants(session_id)")
        cursor.execute("CREATE INDEX idx_votes_session_id ON votes(session_id)")
        cursor.execute("CREATE INDEX idx_votes_participant_id ON votes(participant_id)")
        print("  ✓ Created indexes")
        
        conn.commit()
        
        if create_seed:
            print("\nCreating seed demo session...")
            
            import uuid
            from datetime import timedelta
            
            session_id = f"seed-{uuid.uuid4().hex[:8]}"
            expires_at = datetime.now() + timedelta(hours=2)
            
            cursor.execute("""
                INSERT INTO sessions (id, oom_code, status, created_at, expires_at) 
                VALUES (%s, %s, %s, NOW(), %s)
            """, (session_id, f"oom-{session_id}", 'waiting', expires_at))
            
            conn.commit()
            
            # Create 3 participants (2 human, 1 AI)
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
            
            print(f"  ✓ Created demo session: {session_id}")
            print(f"  ✓ Created participants:")
            for pid, ptype in participant_data:
                icon = "🤖" if ptype == 'ai' else "👤"
                print(f"      {icon} {pid} ({ptype})")
            
            print(f"\n  ✓ WebSocket endpoint: ws://localhost:8000/ws/{session_id}")
            print(f"  ✓ Demo session ready at: http://localhost:3000/{session_id}")
        
        else:
            print("\n✓ Database initialization complete!")
        
    except OperationalError as e:
        print(f"\n✗ Database connection failed: {e}")
        print("   Make sure PostgreSQL is running and accessible.")
        print("   Check DATABASE_URL environment variable.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
    
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize Max Planck Project database")
    parser.add_argument("--seed", action="store_true", help="Create demo session with seed data")
    parser.add_argument("--db", type=str, help="PostgreSQL connection URL (optional)")
    
    args = parser.parse_args()
    
    import datetime
    
    initialize_database(create_seed=args.seed)
