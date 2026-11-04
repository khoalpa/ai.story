from __future__ import annotations

from studio.safe_exit import (
    EXIT_PENDING_KEY,
    SESSION_CLOSED_KEY,
    cancel_exit,
    confirm_exit,
    has_active_job,
    reopen_session,
    request_exit,
)


def test_exit_requires_confirmation_and_can_be_cancelled() -> None:
    state: dict[str, object] = {}

    request_exit(state)
    assert state[EXIT_PENDING_KEY] is True

    cancel_exit(state)
    assert state[EXIT_PENDING_KEY] is False
    assert SESSION_CLOSED_KEY not in state


def test_exit_is_blocked_while_a_job_is_running() -> None:
    state: dict[str, object] = {
        EXIT_PENDING_KEY: True,
        "workspace_last_job_status": "running",
    }

    assert has_active_job(state) is True
    assert confirm_exit(state) is False
    assert state[EXIT_PENDING_KEY] is True
    assert SESSION_CLOSED_KEY not in state


def test_confirmed_exit_is_session_scoped_and_reversible() -> None:
    state: dict[str, object] = {
        EXIT_PENDING_KEY: True,
        "workspace_last_job_status": "completed",
        "studio_prompt_file": "prompt.txt",
    }

    assert confirm_exit(state) is True
    assert state[EXIT_PENDING_KEY] is False
    assert state[SESSION_CLOSED_KEY] is True
    assert state["studio_prompt_file"] == "prompt.txt"

    reopen_session(state)
    assert state[SESSION_CLOSED_KEY] is False
    assert state[EXIT_PENDING_KEY] is False
