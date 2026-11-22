import { useParams } from "react-router-dom";

// Participant page for one Session. Ticket #11 connects it to /ws/{roomCode}
// and renders the Waiting Room / Discussion / Voting / Result views.
export default function RoomPage() {
  const { roomCode } = useParams();
  return (
    <section>
      <h1>Session {roomCode}</h1>
      <p>Connecting…</p>
    </section>
  );
}
