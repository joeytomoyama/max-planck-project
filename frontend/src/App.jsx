import { Navigate, Route, Routes } from "react-router-dom";
import WaitingPage from "./views/WaitingPage.jsx";
import RoomPage from "./views/RoomPage.jsx";

// Two routes, per the spec. The room route renders nested views driven by
// server state (Waiting Room -> Discussion -> Voting -> Result, plus errors).
export default function App() {
  return (
    <main className="app">
      <Routes>
        <Route path="/" element={<Navigate to="/waiting" replace />} />
        <Route path="/waiting" element={<WaitingPage />} />
        <Route path="/room/:roomCode" element={<RoomPage />} />
        <Route path="*" element={<p>Page not found.</p>} />
      </Routes>
    </main>
  );
}
