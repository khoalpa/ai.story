from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, MutableMapping

import streamlit as st

SessionState = MutableMapping[str, Any]


def get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return st.session_state


def append_capped_history_entry(
    history_key: str,
    entry: dict[str, Any],
    *,
    limit: int = 12,
    state: SessionState | None = None,
) -> list[dict[str, Any]]:
    session = get_session_state(state)
    history = list(session.get(history_key) or [])
    history.insert(0, entry)
    session[history_key] = history[:limit]
    return history[:limit]


def append_timestamped_history_entry(
    history_key: str,
    entry: dict[str, Any],
    *,
    limit: int = 12,
    timestamp_key: str = 'time',
    state: SessionState | None = None,
) -> list[dict[str, Any]]:
    payload = dict(entry)
    payload.setdefault(timestamp_key, datetime.now().isoformat(timespec='seconds'))
    return append_capped_history_entry(history_key, payload, limit=limit, state=state)


def append_deduped_tail_history_entry(
    history_key: str,
    entry: dict[str, Any],
    *,
    limit: int = 20,
    dedupe_with_last: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None,
    state: SessionState | None = None,
) -> list[dict[str, Any]]:
    session = get_session_state(state)
    history = list(session.get(history_key) or [])
    if history:
        last = history[-1]
        same = dedupe_with_last(last, entry) if dedupe_with_last is not None else last == entry
        if same:
            return history
    history.append(entry)
    session[history_key] = history[-limit:]
    return list(session[history_key])
