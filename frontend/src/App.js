import React, { useEffect, useRef, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useParams } from 'react-router-dom';

const API_BASE = (process.env.REACT_APP_API_URL || '').replace(/\/$/, '');

function websocketUrl(sessionId) {
  if (!API_BASE) {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${protocol}://${window.location.host}/ws/${sessionId}`;
  }
  return `${API_BASE.replace(/^http/, 'ws')}/ws/${sessionId}`;
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/waiting" replace />} />
        <Route path="/waiting" element={<WaitingRoom />} />
        <Route path="/room/:sessionId" element={<ExperimentRoom />} />
      </Routes>
    </Router>
  );
}

function WaitingRoom() {
  const [roomCode, setRoomCode] = useState('');
  const [config, setConfig] = useState(null);

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.slice(1) || '';
      if (!hash) {
        setConfig(null);
        return;
      }
      const [code, query] = hash.split('?');
      setRoomCode(code);
      const params = query ? `?${query}` : '';
      fetch(`${API_BASE}/api/rooms/${encodeURIComponent(code)}${params}`)
        .then((res) => res.json())
        .then(setConfig)
        .catch(() => setConfig(null));
    };

    window.addEventListener('hashchange', handleHashChange);
    handleHashChange();
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const handleCreate = () => {
    const code = `room${Math.floor(Math.random() * 900) + 100}`;
    setRoomCode(code);
    window.history.replaceState({}, '', `#${code}`);
    fetch(`${API_BASE}/api/rooms/${code}`)
      .then((res) => res.json())
      .then(setConfig)
      .catch(() => setConfig(null));
  };

  if (!roomCode) {
    return (
      <div style={styles.container}>
        <h1>Waiting Room</h1>
        <input
          type="text"
          value={roomCode}
          onChange={(e) => {
            const value = e.target.value;
            setRoomCode(value);
            window.history.replaceState({}, '', value ? `#${value}` : '');
          }}
          placeholder="Enter room code or generate new one"
        />
        <button onClick={handleCreate}>Create New Session</button>
      </div>
    );
  }

  if (config) {
    return (
      <div style={styles.container}>
        <h2>Waiting Room - {roomCode}</h2>
        <p>Time remaining: {Math.ceil((config.time_remaining_seconds || 0) / 60)} min</p>
        <ul>
          {(config.participants || []).map((p) => (
            <li key={p.id}>{p.id}</li>
          ))}
        </ul>
        <button onClick={() => (window.location.hash = '')}>Leave Session</button>
      </div>
    );
  }

  return null;
}

function ExperimentRoom() {
  const { sessionId } = useParams();
  const [session, setSession] = useState(null);
  const [participants, setParticipants] = useState([]);
  const [chatLog, setChatLog] = useState('');
  const [draft, setDraft] = useState('');
  const wsRef = useRef(null);

  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`)
      .then((res) => res.json())
      .then((data) => {
        if (active) {
          setSession(data.session);
          setParticipants(data.participants || []);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [sessionId]);

  useEffect(() => {
    if (!session) return undefined;

    const ws = new WebSocket(websocketUrl(session.id));
    wsRef.current = ws;
    ws.onmessage = (event) => {
      setChatLog((prev) => `${prev}\n${event.data}`.trim());
    };
    ws.onerror = () => {
      if (session.status === 'active') window.location.href = '/waiting';
    };

    return () => {
      wsRef.current = null;
      ws.close();
    };
  }, [session]);

  const handleChat = () => {
    const text = draft.trim();
    if (!text || !wsRef.current) return;
    wsRef.current.send(`chat:${text}`);
    setDraft('');
  };

  if (!session) return <div>Loading...</div>;

  return (
    <div style={styles.container}>
      <h2>Experiment Room {session.id}</h2>
      <p>Status: {session.status}</p>
      <p>Time remaining: {Math.ceil((session.time_remaining_seconds || 0) / 60)} min</p>

      <div style={styles.chat}>
        {chatLog && <pre>{chatLog}</pre>}
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message"
        />
        <button onClick={handleChat}>Send Message</button>
      </div>

      <div style={styles.participants}>
        <h3>Participants</h3>
        <ul>
          {participants.map((p) => (
            <li key={p.id}>{p.id}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

const styles = {
  container: { fontFamily: 'sans-serif', padding: '20px' },
  chat: { marginBottom: '20px' },
  participants: { border: '1px solid #ccc', padding: '10px' },
};

export default App;
