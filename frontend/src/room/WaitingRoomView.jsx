import YouAre from "./YouAre.jsx";

// Shown to a Human after joining, until the Session starts. Deliberately no slot
// count: how many Humans are expected would give away the Condition (Blind
// Condition). The Researcher sees the count on /waiting.
export default function WaitingRoomView({ playerLabel }) {
  return (
    <section>
      <h1>Waiting Room</h1>
      <YouAre playerLabel={playerLabel} />
      <p className="status">Waiting for others to join. The Session starts on its own.</p>
    </section>
  );
}
