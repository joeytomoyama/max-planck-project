import { useEffect, useReducer } from "react";

// One WebSocket per room page. All Session state arrives as server frames and
// is folded into `state` by the reducer; the page never polls. Later tickets
// add cases for phase / chat / vote_recorded / result frames and a `send`.

const initialState = { view: "connecting", playerLabel: null, filled: 0, total: 0, error: null };

function reducer(state, action) {
  switch (action.type) {
    case "joined":
      return { ...state, playerLabel: action.player_label };
    case "waiting":
      return { ...state, view: "waiting", filled: action.filled, total: action.total };
    case "error":
      // An error frame before we joined means the join was refused.
      return state.playerLabel && action.reason === "unsupported" ? state : { ...state, view: "error", error: action.reason };
    case "socket_closed":
      return state.view === "error" ? state : { ...state, view: "error", error: action.reason };
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

  useEffect(() => {
    const ws = new WebSocket(socketUrl(roomCode));
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
      ws.close();
    };
  }, [roomCode]);

  return state;
}
