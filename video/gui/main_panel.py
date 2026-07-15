from __future__ import annotations

import streamlit as st

from video.gui.shared_state import (
    prepare_embedded_view_selection,
    sync_embedded_view_selection,
)

from .tabs import (
    render_doctor_tab,
    render_history_tab,
    render_inputs_tab,
    render_preview_logs_tab,
    render_run_tab,
    render_test_tab,
)

_VIDEO_VIEWS = ["Inputs", "Run", "Doctor", "Test", "Preview & Logs", "History"]


def render_video_main_panel(settings: dict[str, object], *, embedded: bool = False) -> None:
    if embedded:
        _render_embedded_video_panel(settings)
        return
    _render_tabbed_video_panel(settings)


def render_main_panel(settings: dict[str, object], *, embedded: bool = False) -> None:
    render_video_main_panel(settings, embedded=embedded)


def _render_embedded_video_panel(settings: dict[str, object]) -> None:
    prepare_embedded_view_selection(
        app_name="Video",
        widget_key="video_embedded_view_selector",
        options=_VIDEO_VIEWS,
        default="Inputs",
    )

    selected_view = st.radio(
        "Video view",
        options=_VIDEO_VIEWS,
        key="video_embedded_view_selector",
        horizontal=True,
    )
    sync_embedded_view_selection(app_name="Video", widget_value=selected_view)

    if selected_view == "Inputs":
        render_inputs_tab(settings)
        return
    if selected_view == "Run":
        render_run_tab(settings)
        return
    if selected_view == "Doctor":
        render_doctor_tab(settings)
        return
    if selected_view == "Test":
        render_test_tab(settings)
        return
    if selected_view == "History":
        render_history_tab(settings)
        return
    render_preview_logs_tab(settings)


def _render_tabbed_video_panel(settings: dict[str, object]) -> None:
    tab_inputs, tab_run, tab_doctor, tab_test, tab_preview, tab_history = st.tabs(_VIDEO_VIEWS)
    with tab_inputs:
        render_inputs_tab(settings)
    with tab_run:
        render_run_tab(settings)
    with tab_doctor:
        render_doctor_tab(settings)
    with tab_test:
        render_test_tab(settings)
    with tab_preview:
        render_preview_logs_tab(settings)
    with tab_history:
        render_history_tab(settings)
