from __future__ import annotations

import streamlit as st

from .main_panel import render_audio_main_panel
from .settings import get_audio_settings
from .view_models import build_audio_run_summary


def render_audio_workspace(*, embedded: bool = False) -> None:
    settings = get_audio_settings()
    # Widget-owned values can disappear when another Studio workspace is
    # rendered.  Keep a plain snapshot so Overview can always show the current
    # production configuration, even before the first render.
    st.session_state["audio_production_settings"] = build_audio_run_summary(settings)
    render_audio_main_panel(settings, embedded=embedded)


def render_audio_studio(*args, **kwargs):
    return render_audio_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_audio_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_audio_studio(*args, **kwargs)


def main(_args=None) -> None:
    render_audio_workspace()
