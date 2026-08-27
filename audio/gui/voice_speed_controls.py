from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import streamlit as st

from .state import (
    VOICE_EN_FEMALE_SPEED_KEY,
    VOICE_EN_MALE_SPEED_KEY,
    VOICE_EN_NARRATOR_SPEED_KEY,
    VOICE_FEMALE_SPEED_KEY,
    VOICE_MALE_SPEED_KEY,
    VOICE_NARRATOR_SPEED_KEY,
    VOICE_SPEED_DEFAULTS,
)

VOICE_SPEED_MASTER_KEY = "voice_speed_master"
VOICE_SPEED_KEYS = (
    VOICE_NARRATOR_SPEED_KEY,
    VOICE_FEMALE_SPEED_KEY,
    VOICE_MALE_SPEED_KEY,
    VOICE_EN_NARRATOR_SPEED_KEY,
    VOICE_EN_FEMALE_SPEED_KEY,
    VOICE_EN_MALE_SPEED_KEY,
)


def format_voice_speed_percent(value: object) -> str:
    try:
        speed = int(str(value))
    except (TypeError, ValueError):
        speed = 0
    return "0%" if speed == 0 else f"{speed:+d}%"


def apply_voice_speed_master(state: MutableMapping[str, Any] | None = None) -> None:
    target_state = st.session_state if state is None else state
    try:
        master_speed = int(str(target_state.get(VOICE_SPEED_MASTER_KEY, 0)))
    except (TypeError, ValueError):
        master_speed = 0
    master_speed = max(-100, min(100, master_speed))
    target_state[VOICE_SPEED_MASTER_KEY] = master_speed
    for speed_key in VOICE_SPEED_KEYS:
        target_state[speed_key] = master_speed


def render_voice_speed_master(*, defaults: dict) -> int:
    configured_speeds = [int(st.session_state.get(key, defaults.get(key, VOICE_SPEED_DEFAULTS[key]))) for key in VOICE_SPEED_KEYS]
    initial_value = configured_speeds[0] if len(set(configured_speeds)) == 1 else 0
    st.session_state.setdefault(VOICE_SPEED_MASTER_KEY, initial_value)
    return int(st.slider(
        "Voice Speed Master",
        min_value=-100,
        max_value=100,
        key=VOICE_SPEED_MASTER_KEY,
        format="%d%%",
        help="Set the same speed for all 6 voices. You can still fine-tune each voice below.",
        on_change=apply_voice_speed_master,
    ))


def render_voice_speed_slider(*, key: str, default_value: int) -> int:
    current_value = st.session_state.get(key, default_value)
    try:
        current_int = int(current_value)
    except (TypeError, ValueError):
        current_int = int(default_value)
    current_int = max(-100, min(100, current_int))
    st.session_state[key] = current_int
    col_label, col_slider = st.columns([1.6, 5.9], gap="small")
    with col_label:
        st.markdown(
            "<div style='padding-top: 0.42rem; font-size: 0.94rem; line-height: 1.15; white-space: nowrap;'>Speed</div>",
            unsafe_allow_html=True,
        )
    with col_slider:
        return int(st.slider(
            " ", min_value=-100, max_value=100, value=current_int, key=key, label_visibility="collapsed"
        ))
