"""Pure parse of the session-id prefix that broadcast() relies on."""

import main  # noqa: E402


def test_session_id_from_message_handles_string_ids_and_missing_separator():
    assert main.session_id_from_message("oom-42: hello") == "oom-42"
    assert main.session_id_from_message("42: hello") == "42"
    assert main.session_id_from_message("no separator") is None
    assert main.session_id_from_message("") is None
