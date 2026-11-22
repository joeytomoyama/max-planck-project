import YouAre from "./YouAre.jsx";

// Shown to a Human after joining, until the Session starts.
export default function WaitingRoomView({ playerLabel, filled, total }) {
  return (
    <section>
      <h1>Waiting Room</h1>
      <YouAre playerLabel={playerLabel} />
      <p data-testid="slots">
        {filled} of {total} joined
      </p>
      <p className="status">Waiting for others to join. The Session starts on its own.</p>
    </section>
  );
}
