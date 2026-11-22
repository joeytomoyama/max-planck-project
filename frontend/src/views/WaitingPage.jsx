import { useEffect, useState } from "react";

// Researcher page. Ticket #11 adds the "Create Session" button and share link.
// For now it shows whether the backend can reach the database (one fetch on load).
export default function WaitingPage() {
  const [db, setDb] = useState("checking");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((body) => setDb(body.database === "ok" ? "connected" : "unreachable"))
      .catch(() => setDb("unreachable"));
  }, []);

  return (
    <section>
      <h1>Waiting Room</h1>
      <p>Create a Session and share its link with the Humans taking part.</p>
      <p className="status" data-testid="db-status">
        Database: {db}
      </p>
    </section>
  );
}
