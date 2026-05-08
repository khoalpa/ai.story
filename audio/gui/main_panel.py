from __future__ import annotations

import streamlit as st

from audio.gui.workspace_state import (
    prepare_embedded_view_selection,
    sync_embedded_view_selection,
)

from .tabs import render_batch_tab, render_doctor_tab, render_input_tab, render_preview_logs_tab, render_run_tab, render_test_tts_tab

_AUDIO_VIEWS = ["Input", "Run", "Batch", "Doctor", "Test TTS", "Preview & Logs"]


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
        options=_AUDIO_VIEWS,
        default="Input",
    )

    selected_view = st.radio(
        "Audio view",
        options=_AUDIO_VIEWS,
        key="audio_embedded_view_selector",
        horizontal=True,
    )
    sync_embedded_view_selection(app_name="Audio", widget_value=selected_view)

    if selected_view == "Input":
        render_input_tab(settings)
        return
    if selected_view == "Run":
        render_run_tab(settings)
        return
    if selected_view == "Batch":
        render_batch_tab(settings)
        return
    if selected_view == "Doctor":
        render_doctor_tab(settings)
        return
    if selected_view == "Test TTS":
        render_test_tts_tab(settings)
        return
    render_preview_logs_tab(settings)


def _render_tabbed_audio_panel(settings: dict) -> None:
    tab_input, tab_run, tab_batch, tab_doctor, tab_test_tts, tab_preview = st.tabs(_AUDIO_VIEWS)
    with tab_input:
        render_input_tab(settings)
    with tab_run:
        render_run_tab(settings)
    with tab_batch:
        render_batch_tab(settings)
    with tab_doctor:
        render_doctor_tab(settings)
    with tab_test_tts:
        render_test_tts_tab(settings)
    with tab_preview:
        render_preview_logs_tab(settings)
