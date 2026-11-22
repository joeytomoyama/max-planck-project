import { useEffect, useRef, useState } from "react";
import useCountdown from "./useCountdown.js";

// Must match MAX_CHAT_LENGTH in backend/app/session_engine.py (the server also cuts).
const MAX_LENGTH = 500;

const NOTICES = {
  empty_message: "Empty messages are not sent.",
  chat_closed: "The chat is closed.",
};

// Round n's Discussion Phase: countdown, live chat, input. Messages show the
// Player Label and text only, rendered as plain text (React escapes it).
// No typing indicators or other presence signals (Blind Condition).
export default function DiscussionView({ playerLabel, round, deadline, messages, notice, send }) {
  const seconds = useCountdown(deadline);
  const open = seconds > 0;
  const [draft, setDraft] = useState("");
  const listRef = useRef(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  const submit = (e) => {
    e.preventDefault();
    if (!open || !draft.trim()) return;
    send({ type: "chat", text: draft });
    setDraft("");
  };

  return (
    <section>
      <h1 data-testid="round">Round {round}</h1>
      <p className="phase-bar">
        <span data-testid="phase">Discussion</span>
        <span data-testid="countdown" className="countdown">
          {seconds}s left
        </span>
      </p>
      {playerLabel && (
        <p className="label" data-testid="player-label">
          You are <strong>{playerLabel}</strong>
        </p>
      )}
      <ol className="chat" data-testid="chat-log" ref={listRef}>
        {messages.map((m, i) => (
          <li key={i} data-testid="chat-message" className={m.player_label === playerLabel ? "mine" : undefined}>
            <span className="who">{m.player_label}</span>
            <span className="text">{m.text}</span>
          </li>
        ))}
      </ol>
      <form className="chat-input" onSubmit={submit}>
        <input
          data-testid="chat-input"
          aria-label="Message"
          value={draft}
          maxLength={MAX_LENGTH}
          disabled={!open}
          placeholder={open ? "Type a message" : "The discussion has ended"}
          onChange={(e) => setDraft(e.target.value)}
          autoFocus
        />
        <button type="submit" data-testid="chat-send" disabled={!open || !draft.trim()}>
          Send
        </button>
      </form>
      {notice && NOTICES[notice] && <p className="status">{NOTICES[notice]}</p>}
    </section>
  );
}
