import { useState } from "react";

// Researcher page: create a Session and share its link with the Humans.
export default function WaitingPage() {
  const [link, setLink] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function createSession() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/sessions", { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      setLink(body.share_link);
    } catch (e) {
      setError("Could not create a Session. Is the server running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Waiting Room</h1>
      <p>Create a Session and share its link with the Humans taking part.</p>
      <button type="button" onClick={createSession} disabled={busy}>
        Create Session
      </button>
      {link && (
        <div className="share">
          <p>Share this link:</p>
          <a href={link} target="_blank" rel="noreferrer" data-testid="share-link">
            {link}
          </a>
          <button type="button" onClick={() => navigator.clipboard?.writeText(link)}>
            Copy
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
