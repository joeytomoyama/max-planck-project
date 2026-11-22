// Clear message instead of a broken page when a Session can't be joined
// (or the connection is lost). `reason` comes from the server's error frame
// or close code.
const MESSAGES = {
  not_found: ["Session not found", "Check the link you were given."],
  full: ["This Session is full", "All places in this Session are already taken."],
  active: ["This Session has already started", "It can no longer be joined."],
  completed: ["This Session has ended", "It can no longer be joined."],
  expired: ["This Session has expired", "It was closed after a period of inactivity."],
  dropout: ["You can't rejoin this Session", "You left the Session after it started, so you can't take part again."],
  disconnected: ["Connection lost", "The connection to the Session was closed."],
};

export default function ErrorView({ reason }) {
  const [title, detail] = MESSAGES[reason] || ["Something went wrong", "This Session can't be joined."];
  return (
    <section className="error-view" data-testid="error-view" data-reason={reason}>
      <h1>{title}</h1>
      <p>{detail}</p>
    </section>
  );
}
