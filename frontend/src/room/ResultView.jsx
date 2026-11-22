import YouAre from "./YouAre.jsx";

// The Result after Round 2: the Decision Maker and the Votes per Player Label
// from both Rounds combined. Human/AI types appear only when the server sends
// them (`reveal_identities_at_end: true`); otherwise Player Labels only.
export default function ResultView({ playerLabel, result }) {
  const labels = Object.keys(result.counts).sort();
  const types = result.types; // null unless the Researcher turned the reveal on
  return (
    <section>
      <h1>Result</h1>
      <YouAre playerLabel={playerLabel} />
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
              {types && (
                <td data-testid="result-type">{types[label] === "ai" ? "AI Agent" : "Human"}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="status">The Session has ended. Thank you for taking part.</p>
    </section>
  );
}
