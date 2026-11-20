import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';

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
  const [roomCode, setRoomCode] = useState(null);
  const [config, setConfig] = useState(null);

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.slice(1) || '';
      if (hash) {
        const parts = hash.split('?');
        setRoomCode(parts[0]);
        const params = new URLSearchParams(parts[1]).toString();
        fetch(`/api/rooms/${roomCode}?${params}`)
          .then(res => res.json())
          .then(setConfig);
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    handleHashChange();

    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [roomCode]);

  const handleChange = (e) => {
    setRoomCode(e.target.value);
    if (e.target.value) {
      const hash = `#${e.target.value}${window.location.search}`;
      window.history.replaceState({}, '', hash);
    } else {
      window.history.replaceState({}, '', '');
    }
  };

  const handleCreate = () => {
    const parts = ['room', Math.floor(Math.random() * 900) + 100].join('');
    setRoomCode(parts);
    const hash = `#${parts}${window.location.search}`;
    window.history.replaceState({}, '', hash);
    fetch(`/api/rooms/${parts}`)
      .then(res => res.json())
      .then(setConfig);
  };

  if (!roomCode) {
    return (
      <div style={styles.container}>
        <h1>Waiting Room</h1>
        <input type="text" value={roomCode} onChange={handleChange} placeholder="Enter room code or generate new one" />
        <button onClick={handleCreate}>Create New Session</button>
      </div>
    );
  }

  if (config) {
    return (
      <div style={styles.container}>
        <h2>Waiting Room - {roomCode}</h2>
        <p>Time remaining: {Math.ceil(config.time_remaining_seconds / 60)} min</p>
        <ul>
          {config.participants.map(p => (
            <li key={p.participantId}>{p.name} ({p.type})</li>
          ))}
        </ul>
        <button onClick={() => window.location.hash = ''}>Leave Session</button>
      </div>
    );
  }

  return null;
}

function ExperimentRoom() {
  const [session, setSession] = useState(null);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const sessionId = window.location.pathname.split('/').pop();
    
    fetch(`/api/sessions/${sessionId}`)
      .then(res => res.json())
      .then(setSession);

    if (window.location.hash) {
      const params = new URLSearchParams(window.location.hash.slice(1)).toString();
      fetch(`/api/sessions/${sessionId}/config?${params}`)
        .then(res => res.json())
        .then(config => {
          setSession(prev => ({ ...prev, time_remaining: config.time_remaining_seconds }));
        });
    }

    const handleHashChange = () => {
      if (window.location.hash) {
        const params = new URLSearchParams(window.location.hash.slice(1)).toString();
        fetch(`/api/sessions/${sessionId}/config?${params}`)
          .then(res => res.json())
          .then(config => {
            setSession(prev => ({ ...prev, time_remaining: config.time_remaining_seconds }));
          });
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    if (!session) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/${session.id}`);

    ws.onmessage = (event) => {
      setMessage(prev => prev + `\n${event.data}`);
    };

    ws.onerror = () => {
      if (session && session.status === 'active') {
        window.location.href = `/waiting`;
      }
    };

    return () => ws.close();
  }, [session]);

  const handleChat = () => {
    if (message.trim() && session) {
      fetch(`/api/rooms/${session.room_code}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
      }).catch(() => {});
    }
  };

  if (!session) return <div>Loading...</div>;

  return (
    <div style={styles.container}>
      <h2>Experiment Room {session.id}</h2>
      <p>Status: {session.status}</p>
      <p>Time remaining: {Math.ceil(session.time_remaining / 60)} min</p>
      
      <div style={styles.chat}>
        {message && <pre>{message}</pre>}
        <input type="text" value={message} onChange={(e) => setMessage(e.target.value)} />
        <button onClick={handleChat}>Send Message</button>
      </div>

      <div style={styles.participants}>
        <h3>Participants</h3>
        {session.time_remaining > 0 && config && (
          <ul>
            {config.participants.map(p => (
              <li key={p.participantId}>{p.name} ({p.type})</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

const styles = {
  container: { fontFamily: 'sans-serif', padding: '20px' },
  chat: { marginBottom: '20px' },
  participants: { border: '1px solid #ccc', padding: '10px' }
};

export default App;
