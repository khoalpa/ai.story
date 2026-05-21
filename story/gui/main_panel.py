from __future__ import annotations

import streamlit as st

from story.gui.project_tools import render_project_tools_workspace
from story.gui.workspace_state import (
    prepare_embedded_view_selection,
    sync_embedded_view_selection,
)

from .state import STORY_BRIEF_TEXT_KEY, STORY_SYSTEM_PROMPT_TEXT_KEY
from .tabs import render_doctor_tab, render_inputs_tab, render_preview_logs_tab, render_run_tab, render_test_llm_tab, render_tools_tab

_STORY_VIEWS = ["Inputs", "Run", "Tools", "Doctor", "Test LLM", "Preview & Logs", "Project Tools"]


def render_story_main_panel(settings: dict[str, object], *, embedded: bool = False) -> None:
    if embedded:
        _render_embedded_story_panel(settings)
        return
    _render_selectable_story_panel(settings)


def render_main_panel(settings: dict[str, object], *, embedded: bool = False) -> None:
    render_story_main_panel(settings, embedded=embedded)


def _current_story_run_context() -> tuple[str, str]:
    brief_text = st.session_state.get(STORY_BRIEF_TEXT_KEY, "")
    system_prompt = st.session_state.get(STORY_SYSTEM_PROMPT_TEXT_KEY, "")
    return brief_text, system_prompt


def _render_embedded_story_panel(settings: dict[str, object]) -> None:
    prepare_embedded_view_selection(
        app_name="Story",
        widget_key="story_embedded_view_selector",
        options=_STORY_VIEWS,
        default="Inputs",
    )

    selected_view = st.radio(
        "Story view",
        options=_STORY_VIEWS,
        key="story_embedded_view_selector",
        horizontal=True,
    )
    sync_embedded_view_selection(app_name="Story", widget_value=selected_view)

    if selected_view == "Inputs":
        render_inputs_tab(settings)
        return

    brief_text, system_prompt = _current_story_run_context()
    if selected_view == "Run":
        render_run_tab(settings, brief_text=brief_text, system_prompt=system_prompt)
        return
    if selected_view == "Tools":
        render_tools_tab(settings)
        return
    if selected_view == "Doctor":
        render_doctor_tab(settings)
        return
    if selected_view == "Test LLM":
        render_test_llm_tab(settings)
        return
    if selected_view == "Project Tools":
        render_project_tools_workspace(embedded=True)
        return
    render_preview_logs_tab(settings)


def _render_selectable_story_panel(settings: dict[str, object]) -> None:
    selected_view = st.radio(
        "Story view",
        options=_STORY_VIEWS,
        key="story_view_selector",
        horizontal=True,
    )
    if selected_view == "Inputs":
        render_inputs_tab(settings)
        return

    brief_text, system_prompt = _current_story_run_context()
    if selected_view == "Run":
        render_run_tab(settings, brief_text=brief_text, system_prompt=system_prompt)
        return
    if selected_view == "Tools":
        render_tools_tab(settings)
        return
    if selected_view == "Doctor":
        render_doctor_tab(settings)
        return
    if selected_view == "Test LLM":
        render_test_llm_tab(settings)
        return
    if selected_view == "Project Tools":
        render_project_tools_workspace(embedded=True)
        return
    render_preview_logs_tab(settings)
