import useCountdown from "./useCountdown.js";
import YouAre from "./YouAre.jsx";

const NOTICES = {
  vote_closed: "Voting has closed.",
  already_voted: "You have already voted in this Round.",
  bad_vote: "That vote could not be recorded.",
};

// Round n's Voting Phase: one Vote for any Player Label, your own included.
// Once the server acknowledges it, only "Your vote has been recorded" is
// shown: no counts and no other choices until the Result (ADR 0001).
export default function VotingView({ playerLabel, playerLabels, round, deadline, votedRound, notice, send }) {
  const seconds = useCountdown(deadline);
  const voted = votedRound === round;
  const open = seconds > 0 && !voted;

  return (
    <section>
      <h1 data-testid="round">Round {round}</h1>
      <p className="phase-bar">
        <span data-testid="phase">Voting</span>
        <span data-testid="countdown" className="countdown">
          {seconds}s left
        </span>
      </p>
      <YouAre playerLabel={playerLabel} />
      {voted ? (
        <p className="recorded" data-testid="vote-recorded">
          Your vote has been recorded
        </p>
      ) : (
        <>
          <p>Who should be the Decision Maker?</p>
          <div className="ballot">
            {playerLabels.map((label) => (
              <button
                key={label}
                type="button"
                data-testid="ballot-option"
                disabled={!open}
                onClick={() => send({ type: "vote", target: label })}
              >
                {label}
                {label === playerLabel ? " (you)" : ""}
              </button>
            ))}
          </div>
          {notice && NOTICES[notice] && <p className="status">{NOTICES[notice]}</p>}
        </>
      )}
    </section>
  );
}
