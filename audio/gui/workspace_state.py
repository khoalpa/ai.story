from __future__ import annotations

import streamlit as st

from audio.gui.global_run_monitor import (
    WORKSPACE_JOB_TIMELINE_KEY,
    WORKSPACE_LAST_JOB_APP_KEY,
    WORKSPACE_LAST_JOB_ERROR_KEY,
    WORKSPACE_LAST_JOB_OUTPUT_KEY,
    WORKSPACE_LAST_JOB_PROGRESS_KEY,
    WORKSPACE_LAST_JOB_STAGE_KEY,
    WORKSPACE_LAST_JOB_STATUS_KEY,
    WORKSPACE_LAST_JOB_SUMMARY_KEY,
    global_run_monitor_state,
)
from audio.gui.workspace_navigation import workspace_navigation_state


def ensure_workspace_state() -> None:
    defaults = {
        "workspace_audio_target_view": "inputs",
        "workspace_video_target_view": "inputs",
        "workspace_audio_target_field": "",
        "workspace_video_target_field": "",
        "workspace_audio_output_path": "",
        "workspace_audio_srt_path": "",
        WORKSPACE_LAST_JOB_APP_KEY: "",
        WORKSPACE_LAST_JOB_STAGE_KEY: "",
        WORKSPACE_LAST_JOB_STATUS_KEY: "idle",
        WORKSPACE_LAST_JOB_PROGRESS_KEY: 0,
        WORKSPACE_LAST_JOB_OUTPUT_KEY: "",
        WORKSPACE_LAST_JOB_ERROR_KEY: "",
        WORKSPACE_LAST_JOB_SUMMARY_KEY: None,
        WORKSPACE_JOB_TIMELINE_KEY: [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def get_workspace_target_view(app_name: str, default: str = "Run") -> str:
    ensure_workspace_state()
    return workspace_navigation_state(st.session_state).get_target_view(app_name, default)


def set_workspace_target_view(app_name: str, value: str) -> None:
    ensure_workspace_state()
    workspace_navigation_state(st.session_state).set_target_view(app_name, value)


def get_workspace_target_field(app_name: str, default: str = "") -> str:
    ensure_workspace_state()
    return workspace_navigation_state(st.session_state).get_target_field(app_name, default)


def prepare_embedded_view_selection(*, app_name: str, widget_key: str, options: list[str], default: str, normalize=lambda value: value) -> str:
    target = normalize(get_workspace_target_view(app_name, default))
    if target not in options:
        target = default
    current = normalize(st.session_state.get(widget_key, ""))
    if current in options:
        st.session_state[widget_key] = current
    else:
        st.session_state[widget_key] = target
    return target


def sync_embedded_view_selection(*, app_name: str, widget_value: str) -> None:
    set_workspace_target_view(app_name, widget_value)


def set_audio_handoff(*, audio_output_path: str, srt_output_path: str = "") -> None:
    ensure_workspace_state()
    st.session_state["workspace_audio_output_path"] = audio_output_path or ""
    st.session_state["workspace_audio_srt_path"] = srt_output_path or ""


def send_audio_to_video(*, audio_output_path: str, srt_output_path: str = "") -> None:
    set_audio_handoff(audio_output_path=audio_output_path, srt_output_path=srt_output_path)
    navigation = workspace_navigation_state(st.session_state)
    navigation.set_target_view("Video", "inputs")


def ensure_global_run_monitor_state() -> None:
    ensure_workspace_state()


def update_global_run_monitor(*, app: str, stage: str, status: str, progress: int | float = 0, output_path: str = "", error_text: str = "", summary: dict | None = None) -> None:
    ensure_global_run_monitor_state()
    monitor = global_run_monitor_state(st.session_state)
    monitor.app, monitor.stage, monitor.status = app, stage, status
    monitor.progress, monitor.output, monitor.error, monitor.summary = progress, output_path, error_text, summary


def append_global_run_event(*, app: str, stage: str, status: str, message: str = "", output_path: str = "", error_text: str = "") -> None:
    ensure_global_run_monitor_state()
    global_run_monitor_state(st.session_state).append_timeline_event(
        app=app, stage=stage, status=status, message=message,
        output_path=output_path, error_text=error_text,
    )
