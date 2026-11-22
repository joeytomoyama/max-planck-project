import { useParams } from "react-router-dom";
import useRoomSocket from "../room/useRoomSocket.js";
import WaitingRoomView from "../room/WaitingRoomView.jsx";
import ErrorView from "../room/ErrorView.jsx";

// Participant page for one Session. Renders the view the server state calls
// for: Waiting Room -> (Discussion -> Voting) x2 -> Result, or an error view.
export default function RoomPage() {
  const { roomCode } = useParams();
  const state = useRoomSocket(roomCode);

  switch (state.view) {
    case "waiting":
      return <WaitingRoomView playerLabel={state.playerLabel} filled={state.filled} total={state.total} />;
    case "error":
      return <ErrorView reason={state.error} />;
    default:
      return (
        <section>
          <h1>Joining Session…</h1>
        </section>
      );
  }
}
