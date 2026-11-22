// The Result after Round 2: the Decision Maker and the Votes per Player Label
// from both Rounds combined. Player Labels only (no Human/AI types).
export default function ResultView({ playerLabel, result }) {
  const labels = Object.keys(result.counts).sort();
  return (
    <section>
      <h1>Result</h1>
      {playerLabel && (
        <p className="label" data-testid="player-label">
          You are <strong>{playerLabel}</strong>
        </p>
      )}
      <p className="decision-maker" data-testid="decision-maker">
        Decision Maker: <strong>{result.decision_maker}</strong>
      </p>
      <table className="counts">
        <caption>Votes across both Rounds</caption>
        <tbody>
          {labels.map((label) => (
            <tr key={label} data-testid="result-count" data-label={label}>
              <th scope="row">{label}</th>
              <td>{result.counts[label]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="status">The Session has ended. Thank you for taking part.</p>
    </section>
  );
}
