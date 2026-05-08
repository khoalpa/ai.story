from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import streamlit as st

from .panel_utils import safe_rerun
from .user_messages import UserMessage, render_user_message


@dataclass(frozen=True)
class ProviderAction:
    action_id: str
    label: str
    key: str
    callback: Callable[[], None]


def set_action_status(status_key: str, level: str, message: str) -> None:
    st.session_state[status_key] = (level, message)


def render_action_status(status_key: str) -> None:
    payload = st.session_state.get(status_key)
    if not isinstance(payload, tuple) or len(payload) != 2:
        return
    level, message = payload
    render_user_message(UserMessage(level=str(level or "info"), title="Action status", body=str(message or "")))


def render_provider_action_row(actions: Iterable[ProviderAction], *, rerun_after_click: bool = True) -> str | None:
    action_list = list(actions)
    if not action_list:
        return None
    cols = st.columns(len(action_list))
    clicked_action: str | None = None
    for col, action in zip(cols, action_list):
        if col.button(action.label, key=action.key, width="stretch"):
            action.callback()
            clicked_action = action.action_id
            if rerun_after_click:
                safe_rerun()
            break
    return clicked_action
