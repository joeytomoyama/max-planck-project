import useCountdown from "./useCountdown.js";

// Round n's Voting Phase. Placeholder until ticket #13 adds the ballot:
// the chat is closed and the server's countdown runs.
export default function VotingView({ playerLabel, round, deadline }) {
  const seconds = useCountdown(deadline);
  return (
    <section>
      <h1 data-testid="round">Round {round}</h1>
      <p className="phase-bar">
        <span data-testid="phase">Voting</span>
        <span data-testid="countdown" className="countdown">
          {seconds}s left
        </span>
      </p>
      {playerLabel && (
        <p className="label" data-testid="player-label">
          You are <strong>{playerLabel}</strong>
        </p>
      )}
      <p className="status">The discussion has ended. Voting opens here.</p>
    </section>
  );
}
