-- Seed Data Script for Max Planck Project Demo Session
-- This creates a demo session with 3 participants for local testing

-- Parameters (set as environment variables or adjust in script)
-- SESSION_ID: The unique identifier for the demo session (auto-generated if not provided)
-- PARTICIPANT_TYPES: Comma-separated list like "human,human,ai" (defaults to 2 human, 1 AI)

DO $$
DECLARE
    v_session_id TEXT;
    v_oom_code TEXT;
    v_expires_at TIMESTAMP;
    v_participant_types TEXT := 'human,human,ai'; -- Default: 2 humans, 1 AI
    v_participant_data RECORD;
BEGIN
    -- Get or generate session ID
    v_session_id := COALESCE(
        -- Use provided SESSION_ID if set, otherwise generate one
        CURRENT_SETTING('session_id')::TEXT,
        'seed-' || LEFT(gen_random_text_char(8), 8)
    );
    
    -- Generate oom_code from session_id
    v_oom_code := 'oom-' || v_session_id;
    
    -- Set expiration (2 hours from now by default)
    v_expires_at := NOW() + INTERVAL '2 hours';
    
    -- Insert demo session
    INSERT INTO sessions (id, oom_code, status, created_at, expires_at)
    VALUES (v_session_id, v_oom_code, 'waiting', NOW(), v_expires_at);
    
    -- Split participant types into array
    FOR v_participant_data IN 
        SELECT * FROM unnist(text_split(v_participant_types::TEXT, ',')) WITH NO ESCAPE AS tp(row)
    LOOP
        INSERT INTO participants (session_id, id, type, joined_at, last_activity)
        VALUES (v_session_id, v_participant_data.row, v_participant_data.type, NOW(), NOW());
    END LOOP;
    
    -- Use simple approach if WITH NO ESCAPE not supported
    FOR i IN 1 .. string_length('human,human,ai') - string_length(replace('human,human,ai', ',')) + 1 LOOP
        INSERT INTO participants (session_id, id, type, joined_at, last_activity)
        VALUES (v_session_id, 'Player ' || i::TEXT, 
            CASE WHEN mod(i - 1, 3) = 0 THEN 'human' 
                 WHEN mod(i - 1, 3) = 1 THEN 'human'
                 ELSE 'ai' END,
            NOW(), NOW());
    END LOOP;
    
    -- Insert with correct logic (simplified for PostgreSQL compatibility)
    DELETE FROM participants WHERE session_id = v_session_id;
    
    FOR i IN 1 .. 3 LOOP
        INSERT INTO participants (session_id, id, type, joined_at, last_activity)
        VALUES (v_session_id, 'Player ' || i::TEXT,
            CASE i 
                WHEN 1 THEN 'human'
                WHEN 2 THEN 'human'
                ELSE 'ai'
            END,
            NOW(), NOW());
    END LOOP;
    
    RAISE NOTICE 'Seed session created successfully!';
    RAISE NOTICE '  Session ID: %', v_session_id;
    RAISE NOTICE '  OOM Code: %', v_oom_code;
    RAISE NOTICE '  Expires at: %', TO_CHAR(v_expires_at, 'YYYY-MM-DD HH24:MI:SS');
    
END $$;
