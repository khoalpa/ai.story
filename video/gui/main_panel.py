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
from .view_registry import (
    VIDEO_VIEW_BY_ID,
    VIDEO_VIEW_IDS,
    VIDEO_VIEW_SPECS,
    normalize_video_view_id,
)

_VIDEO_RENDERERS = {
    "inputs": render_inputs_tab,
    "run": render_run_tab,
    "doctor": render_doctor_tab,
    "test": render_test_tab,
    "results_logs": render_preview_logs_tab,
    "history": render_history_tab,
}


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
        options=list(VIDEO_VIEW_IDS),
        default="inputs",
        normalize=normalize_video_view_id,
    )

    selected_view = st.segmented_control(
        "Khu vực",
        options=VIDEO_VIEW_IDS,
        key="video_embedded_view_selector",
        format_func=lambda view_id: VIDEO_VIEW_BY_ID[view_id].label,
    ) or "inputs"
    sync_embedded_view_selection(app_name="Video", widget_value=selected_view)

    _VIDEO_RENDERERS[selected_view](settings)


def _render_tabbed_video_panel(settings: dict[str, object]) -> None:
    tabs = st.tabs([spec.label for spec in VIDEO_VIEW_SPECS])
    for tab, spec in zip(tabs, VIDEO_VIEW_SPECS):
        with tab:
            _VIDEO_RENDERERS[spec.id](settings)
