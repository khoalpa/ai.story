from __future__ import annotations

import streamlit as st

from .main_panel import render_video_main_panel
from .settings import get_video_settings

APP_TITLE = "Render Video Workspace"


def render_video_workspace(*, embedded: bool = False) -> None:
    if not embedded:
        st.set_page_config(page_title=APP_TITLE, page_icon=":material/movie:", layout="wide")
        st.title(APP_TITLE)
        st.caption("Unified GUI for the audio -> MP4 pipeline, including preview, logs, and history.")
    else:
        st.subheader(APP_TITLE)
        st.caption("Audio -> MP4 pipeline with static/slideshow mode")

    settings = get_video_settings()
    render_video_main_panel(settings, embedded=embedded)


def render_video_studio(*args, **kwargs):
    return render_video_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_video_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_video_studio(*args, **kwargs)


def main(_args=None) -> None:
    render_video_workspace(embedded=False)
