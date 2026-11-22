// "You are Player X": the Human's own Player Label, shown in every Room view.
export default function YouAre({ playerLabel }) {
  if (!playerLabel) return null;
  return (
    <p className="label" data-testid="player-label">
      You are <strong>{playerLabel}</strong>
    </p>
  );
}
