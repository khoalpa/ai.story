from __future__ import annotations

import streamlit as st

from audio.gui.workspace_state import (
    prepare_embedded_view_selection,
    sync_embedded_view_selection,
)

from .tabs import (
    render_batch_tab,
    render_doctor_tab,
    render_history_tab,
    render_input_tab,
    render_preview_logs_tab,
    render_run_tab,
    render_test_tts_tab,
)
from .view_registry import (
    AUDIO_VIEW_BY_ID,
    AUDIO_VIEW_IDS,
    AUDIO_VIEW_SPECS,
    normalize_audio_view_id,
)

_AUDIO_RENDERERS = {
    "inputs": render_input_tab,
    "run": render_run_tab,
    "batch": render_batch_tab,
    "doctor": render_doctor_tab,
    "test": render_test_tts_tab,
    "results_logs": render_preview_logs_tab,
    "history": render_history_tab,
}


def render_audio_main_panel(settings: dict, *, embedded: bool = False) -> None:
    if embedded:
        _render_embedded_audio_panel(settings)
        return
    _render_tabbed_audio_panel(settings)


def render_main_panel(settings: dict, *, embedded: bool = False) -> None:
    render_audio_main_panel(settings, embedded=embedded)


def _render_embedded_audio_panel(settings: dict) -> None:
    prepare_embedded_view_selection(
        app_name="Audio",
        widget_key="audio_embedded_view_selector",
        options=list(AUDIO_VIEW_IDS),
        default="inputs",
        normalize=normalize_audio_view_id,
    )

    selected_view = st.segmented_control(
        "Khu vực",
        options=AUDIO_VIEW_IDS,
        key="audio_embedded_view_selector",
        format_func=lambda view_id: AUDIO_VIEW_BY_ID[view_id].label,
    ) or "inputs"
    sync_embedded_view_selection(app_name="Audio", widget_value=selected_view)

    _AUDIO_RENDERERS[selected_view](settings)


def _render_tabbed_audio_panel(settings: dict) -> None:
    tabs = st.tabs([spec.label for spec in AUDIO_VIEW_SPECS])
    for tab, spec in zip(tabs, AUDIO_VIEW_SPECS):
        with tab:
            _AUDIO_RENDERERS[spec.id](settings)
