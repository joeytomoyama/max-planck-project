import { useCallback, useEffect, useReducer, useRef } from "react";

// One WebSocket per room page. All Session state arrives as server frames and
// is folded into `state` by the reducer; the page never polls. `send` writes a
// client frame (e.g. `{type: "chat", text}` or `{type: "vote", target}`).

const initialState = {
  view: "connecting", // connecting | waiting | discussion | voting | result | error
  playerLabel: null,
  playerLabels: [], // every Player Label in the Session (the ballot)
  votedRound: null, // Round whose Vote the server acknowledged
  result: null, // {counts: {"Player X": n}, decision_maker, types: {"Player X": "human"|"ai"} only if the reveal is on}
  filled: 0,
  total: 0,
  round: null,
  deadline: null, // server deadline of the current Phase, in *client* clock ms
  messages: [], // [{player_label, text, sent_at}] of the current Round's Discussion Phase
  notice: null, // last non-fatal error reason (e.g. empty_message, chat_closed)
  error: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "joined":
      return { ...state, playerLabel: action.player_label };
    case "waiting":
      return { ...state, view: "waiting", filled: action.filled, total: action.total };
    case "phase": {
      // Shift the server deadline by the measured clock offset so every client
      // counts down to the same instant whatever its own clock says.
      const offset = Date.now() - Date.parse(action.server_time);
      const newRound = action.round !== state.round;
      return {
        ...state,
        view: action.phase,
        round: action.round,
        deadline: Date.parse(action.deadline) + offset,
        playerLabels: action.player_labels || state.playerLabels,
        messages: newRound ? [] : state.messages,
        notice: null,
      };
    }
    case "chat":
      return {
        ...state,
        messages: [...state.messages, { player_label: action.player_label, text: action.text, sent_at: action.sent_at }],
      };
    case "vote_recorded":
      return { ...state, votedRound: action.round };
    case "result":
      return { ...state, view: "result", result: { counts: action.counts, decision_maker: action.decision_maker, types: action.types || null } };
    case "closed":
      return { ...state, view: "error", error: action.reason };
    case "error":
      // Before we joined, an error means the join was refused; afterwards it is
      // a rejected frame (empty chat message, chat closed, ...) and not fatal.
      return state.playerLabel ? { ...state, notice: action.reason } : { ...state, view: "error", error: action.reason };
    case "socket_closed":
      // After the Result the server may close the socket; keep showing the Result.
      return state.view === "error" || state.view === "result" ? state : { ...state, view: "error", error: action.reason };
    default:
      return state;
  }
}

// Close codes the server uses for refused joins (see backend/app/realtime.py).
const CLOSE_REASONS = { 4404: "not_found", 4409: "full", 4423: "active", 4410: "completed", 4408: "expired" };

export function socketUrl(roomCode) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/${encodeURIComponent(roomCode)}`;
}

export default function useRoomSocket(roomCode) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(socketUrl(roomCode));
    wsRef.current = ws;
    let closedByUs = false;
    ws.onopen = () => ws.send(JSON.stringify({ type: "join" }));
    ws.onmessage = (msg) => {
      try {
        dispatch(JSON.parse(msg.data));
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = (ev) => {
      if (!closedByUs) dispatch({ type: "socket_closed", reason: CLOSE_REASONS[ev.code] || "disconnected" });
    };
    return () => {
      closedByUs = true;
      wsRef.current = null;
      ws.close();
    };
  }, [roomCode]);

  const send = useCallback((frame) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(frame));
  }, []);

  return [state, send];
}
