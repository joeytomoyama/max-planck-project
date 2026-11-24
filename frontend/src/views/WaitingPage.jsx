import { useEffect, useState } from "react";

const POLL_MS = 1000;

// Researcher page: create a Session, share its link with the Humans, and watch
// its Waiting Room fill. The Condition and the slot count are shown only here:
// they come from a Researcher-only endpoint that needs the token returned when
// the Session is created (never in the share link, Blind Condition).
export default function WaitingPage() {
  const [created, setCreated] = useState(null); // {share_link, room_code, researcher_token}
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const status = useResearcherStatus(created);

  async function createSession() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/sessions", { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setCreated(await res.json());
    } catch (e) {
      setError("Could not create a Session. Is the server running?");
    } finally {
      setBusy(false);
    }
  }

  const link = created?.share_link;
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
      {link && <SessionStatus status={status} />}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function SessionStatus({ status }) {
  if (!status) return <p className="status">Loading Session status…</p>;
  if (status.error) return <p className="error">{status.error}</p>;
  return (
    <div className="session-status">
      <p data-testid="condition">
        Condition: <strong>{status.condition.description}</strong>
      </p>
      <p data-testid="slots">{progressText(status)}</p>
    </div>
  );
}

function progressText({ status, filled, total }) {
  switch (status) {
    case "waiting":
      return `${filled} of ${total} Humans joined`;
    case "active":
      return "All Humans joined. The Session has started.";
    case "completed":
      return "The Session has started and is now finished.";
    case "expired":
      return "This Session has expired.";
    default:
      return status;
  }
}

// Polls the Researcher status of `created` until the Session leaves the Waiting Room.
function useResearcherStatus(created) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    setStatus(null);
    if (!created) return undefined;
    let stopped = false;
    let timer = null;
    const url = `/api/sessions/${encodeURIComponent(created.room_code)}/researcher`;

    async function poll() {
      let next;
      try {
        const res = await fetch(url, { headers: { "X-Researcher-Token": created.researcher_token } });
        next = res.ok ? await res.json() : { error: `Could not load the Session status (HTTP ${res.status}).` };
      } catch {
        next = { error: "Could not reach the server. Retrying…", retry: true };
      }
      if (stopped) return;
      setStatus(next);
      if (next.status === "waiting" || next.retry) timer = setTimeout(poll, POLL_MS);
    }

    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [created]);

  return status;
}
