from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import streamlit as st

from .panel_utils import safe_rerun


@dataclass(frozen=True)
class HandoffAction:
    label: str
    key: str
    callback: Callable[[], None]
    success_message: str
    rerun_after_click: bool = True
    disabled: bool = False


def render_handoff_action_row(actions: Iterable[HandoffAction], *, column_spec: list[float] | None = None) -> str | None:
    action_list = list(actions)
    if not action_list:
        return None
    cols = st.columns(column_spec or [1.0] * len(action_list))
    clicked_key: str | None = None
    for col, action in zip(cols, action_list):
        with col:
            if st.button(action.label, width="stretch", key=action.key, disabled=action.disabled):
                action.callback()
                st.success(action.success_message)
                clicked_key = action.key
                if action.rerun_after_click:
                    safe_rerun()
                break
    return clicked_key
