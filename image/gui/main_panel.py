from __future__ import annotations

import streamlit as st

from common.gui.state import prepare_embedded_view_selection, sync_embedded_view_selection

from .tabs import (
    render_doctor_tab,
    render_history_tab,
    render_inpaint_tab,
    render_inputs_tab,
    render_preview_logs_tab,
    render_prompt_tab,
    render_run_tab,
    render_test_tab,
)
from .upscale_tab import render_upscale_tab

_IMAGE_VIEWS = ["Inputs", "Prompt", "Inpaint", "Run", "Upscale", "Doctor", "Test", "Preview & Logs", "History"]


def render_image_main_panel(settings: dict[str, object], *, embedded: bool = False) -> None:
    if embedded:
        _render_embedded_image_panel(settings)
        return
    _render_tabbed_image_panel(settings)


def render_main_panel(settings: dict[str, object], *, embedded: bool = False) -> None:
    render_image_main_panel(settings, embedded=embedded)


def _render_embedded_image_panel(settings: dict[str, object]) -> None:
    prepare_embedded_view_selection(
        app_name="Image",
        widget_key="image_embedded_view_selector",
        options=_IMAGE_VIEWS,
        default="Inputs",
    )
    selected_view = st.radio(
        "Image view",
        options=_IMAGE_VIEWS,
        key="image_embedded_view_selector",
        horizontal=True,
    )
    sync_embedded_view_selection(app_name="Image", widget_value=selected_view)

    if selected_view == "Inputs":
        render_inputs_tab(settings)
        return
    if selected_view == "Prompt":
        render_prompt_tab(settings)
        return
    if selected_view == "Inpaint":
        render_inpaint_tab(settings)
        return
    if selected_view == "Run":
        render_run_tab(settings)
        return
    if selected_view == "Upscale":
        render_upscale_tab(settings)
        return
    if selected_view == "Doctor":
        render_doctor_tab(settings)
        return
    if selected_view == "Test":
        render_test_tab(settings)
        return
    if selected_view == "Preview & Logs":
        render_preview_logs_tab(settings)
        return
    render_history_tab(settings)


def _render_tabbed_image_panel(settings: dict[str, object]) -> None:
    tab_inputs, tab_prompt, tab_inpaint, tab_run, tab_upscale, tab_doctor, tab_test, tab_preview, tab_history = st.tabs(_IMAGE_VIEWS)
    with tab_inputs:
        render_inputs_tab(settings)
    with tab_prompt:
        render_prompt_tab(settings)
    with tab_inpaint:
        render_inpaint_tab(settings)
    with tab_run:
        render_run_tab(settings)
    with tab_upscale:
        render_upscale_tab(settings)
    with tab_doctor:
        render_doctor_tab(settings)
    with tab_test:
        render_test_tab(settings)
    with tab_preview:
        render_preview_logs_tab(settings)
    with tab_history:
        render_history_tab(settings)

