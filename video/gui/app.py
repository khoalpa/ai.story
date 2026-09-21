from __future__ import annotations

import streamlit as st

from studio.ui_components import render_workspace_header

from .main_panel import render_video_main_panel
from .settings import get_video_settings
from .state import capture_project_path_defaults
from .view_models import _VIDEO_SETTINGS_FIELDS

APP_TITLE = "Không gian sản xuất video"


def render_video_workspace(*, embedded: bool = False) -> None:
    if not embedded:
        st.set_page_config(page_title=APP_TITLE, page_icon=":material/movie:", layout="wide")
        st.title(APP_TITLE)
        st.caption("Tạo MP4 từ audio, phụ đề và hình ảnh; hỗ trợ xem trước, nhật ký và lịch sử.")
    else:
        render_workspace_header(
            "Video",
            "Kiểm tra audio, phụ đề và hình ảnh trước khi render hoặc ghép video đầu ra.",
            eyebrow="Sản xuất",
        )


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
