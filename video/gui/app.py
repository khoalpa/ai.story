from __future__ import annotations

import streamlit as st

from .main_panel import render_video_main_panel
from .settings import get_video_settings
from .state import capture_project_path_defaults
from .view_models import _VIDEO_SETTINGS_FIELDS

APP_TITLE = "Render Video Workspace"


def render_video_workspace(*, embedded: bool = False) -> None:
    if not embedded:
        st.set_page_config(page_title=APP_TITLE, page_icon=":material/movie:", layout="wide")
        st.title(APP_TITLE)
        st.caption("Unified GUI for the audio -> MP4 pipeline, including preview, logs, and history.")


    settings = get_video_settings()
    # Preserve non-widget configuration for the project Overview. Streamlit
    # removes widget keys while the Video workspace is not being rendered.
    st.session_state["video_production_settings"] = {
        key: settings.get(key) for key in _VIDEO_SETTINGS_FIELDS
    }
    render_video_main_panel(settings, embedded=embedded)
    capture_project_path_defaults()


def render_video_studio(*args, **kwargs):
    return render_video_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_video_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_video_studio(*args, **kwargs)


def main(_args=None) -> None:
    render_video_workspace(embedded=False)
