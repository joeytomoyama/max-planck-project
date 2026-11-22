import { useParams } from "react-router-dom";
import useRoomSocket from "../room/useRoomSocket.js";
import WaitingRoomView from "../room/WaitingRoomView.jsx";
import DiscussionView from "../room/DiscussionView.jsx";
import VotingView from "../room/VotingView.jsx";
import ErrorView from "../room/ErrorView.jsx";

// Participant page for one Session. Renders the view the server state calls
// for: Waiting Room -> (Discussion -> Voting) x2 -> Result, or an error view.
export default function RoomPage() {
  const { roomCode } = useParams();
  const [state, send] = useRoomSocket(roomCode);

  switch (state.view) {
    case "waiting":
      return <WaitingRoomView playerLabel={state.playerLabel} filled={state.filled} total={state.total} />;
    case "discussion":
      return (
        <DiscussionView
          playerLabel={state.playerLabel}
          round={state.round}
          deadline={state.deadline}
          messages={state.messages}
          notice={state.notice}
          send={send}
        />
      );
    case "voting":
      return <VotingView playerLabel={state.playerLabel} round={state.round} deadline={state.deadline} />;
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
