// Shown to a Human after joining, until the Session starts.
export default function WaitingRoomView({ playerLabel, filled, total }) {
  return (
    <section>
      <h1>Waiting Room</h1>
      {playerLabel && (
        <p className="label" data-testid="player-label">
          You are <strong>{playerLabel}</strong>
        </p>
      )}
      <p data-testid="slots">
        {filled} of {total} joined
      </p>
      <p className="status">Waiting for others to join. The Session starts on its own.</p>
    </section>
  );
}
