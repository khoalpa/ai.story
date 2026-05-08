from __future__ import annotations

from typing import Any

import streamlit as st

from common.gui.provider_actions import ProviderAction, render_action_status, render_provider_action_row, set_action_status
from common.model_store import list_local_models, list_local_targets, provider_models_dir, provider_target_dir
from common.runtime_diagnostics import RuntimeDiagnosticsReport
from video.config import get_ffmpeg_exe, get_ffprobe_exe
from video.providers.base import VideoProviderDescriptor, VideoProviderSettings
from video.runtime_tools import collect_runtime_diagnostics, describe_tool

PROVIDER_ID = "ffmpeg_local"
STATUS_KEY = "video_provider_action_status"


def _render_runtime_target_picker(ffmpeg_exe: str, ffprobe_exe: str) -> tuple[str, str, str]:
    target_dir = provider_target_dir("video", PROVIDER_ID, __file__)
    local_targets = list_local_targets("video", __file__, provider_id=PROVIDER_ID, max_depth=3)
    options = ["(manual)", *local_targets]
    key = f"video_runtime_target::{PROVIDER_ID}"
    selected = str(st.session_state.get(key) or "(manual)")
    if selected not in options:
        selected = "(manual)"
    selected = st.selectbox(
        "Local runtime target",
        options=options,
        index=options.index(selected),
        key=key,
        help="Scan from video/local_models/ffmpeg_local/. You can place ffmpeg.exe / ffprobe.exe or a full runtime folder here.",
    )
    st.caption(f"Update target: {target_dir}")
    if local_targets:
        suffix = " ..." if len(local_targets) > 6 else ""
        st.caption(f"Scanned local targets: {', '.join(local_targets[:6])}{suffix}")
    if selected != "(manual)":
        base = target_dir / selected.rstrip("/")
        if base.is_dir():
            ffmpeg_candidate = base / "ffmpeg.exe"
            ffprobe_candidate = base / "ffprobe.exe"
            if ffmpeg_candidate.exists():
                ffmpeg_exe = str(ffmpeg_candidate)
            if ffprobe_candidate.exists():
                ffprobe_exe = str(ffprobe_candidate)
        elif base.is_file() and base.name.lower().startswith("ffmpeg"):
            ffmpeg_exe = str(base)
    return ffmpeg_exe, ffprobe_exe, str(target_dir)


def _render_provider_actions(*, ffmpeg_exe: str, ffprobe_exe: str) -> None:
    def _refresh() -> None:
        models_dir = provider_models_dir("video", __file__)
        list_local_models("video", __file__)
        set_action_status(STATUS_KEY, "success", f"Video: refreshed {PROVIDER_ID} - models dir={models_dir}")

    def _test() -> None:
        info = collect_runtime_diagnostics(ffmpeg_exe=ffmpeg_exe, ffprobe_exe=ffprobe_exe)
        ffmpeg_ok = bool(getattr(info, "ffmpeg_exists", False))
        ffprobe_ok = bool(getattr(info, "ffprobe_exists", False))
        if ffmpeg_ok and ffprobe_ok:
            set_action_status(
                STATUS_KEY,
                "success",
                f"Video: test {PROVIDER_ID} OK | ffmpeg={describe_tool(ffmpeg_exe)} | ffprobe={describe_tool(ffprobe_exe)}",
            )
        else:
            set_action_status(
                STATUS_KEY,
                "error",
                f"Video: test {PROVIDER_ID} failed | ffmpeg={describe_tool(ffmpeg_exe)} | ffprobe={describe_tool(ffprobe_exe)}",
            )

    def _update() -> None:
        target_dir = provider_target_dir("video", PROVIDER_ID, __file__)
        set_action_status(
            STATUS_KEY,
            "success",
            f"Video: Update does not download binaries from the internet. Update target={target_dir}.",
        )

    render_provider_action_row(
        [
            ProviderAction("refresh", "Refresh", key=f"video_provider_refresh::{PROVIDER_ID}", callback=_refresh),
            ProviderAction("test", "Test", key=f"video_provider_test::{PROVIDER_ID}", callback=_test),
            ProviderAction("update", "Update", key=f"video_provider_update::{PROVIDER_ID}", callback=_update),
        ]
    )
    render_action_status(STATUS_KEY)


def render_sidebar() -> VideoProviderSettings:
    st.caption(f"Models dir: {provider_models_dir('video', __file__)}")
    ffmpeg_exe, ffprobe_exe, local_update_target = _render_runtime_target_picker(get_ffmpeg_exe(), get_ffprobe_exe())
    ffmpeg_exe = st.text_input("ffmpeg executable", value=ffmpeg_exe)
    ffprobe_exe = st.text_input("ffprobe executable", value=ffprobe_exe)
    _render_provider_actions(ffmpeg_exe=ffmpeg_exe, ffprobe_exe=ffprobe_exe)
    st.caption(f"ffmpeg -> {describe_tool(ffmpeg_exe)}")
    st.caption(f"ffprobe -> {describe_tool(ffprobe_exe)}")
    return VideoProviderSettings(
        provider=PROVIDER_ID,
        ffmpeg_exe=ffmpeg_exe,
        ffprobe_exe=ffprobe_exe,
        local_update_target=local_update_target,
    )


def collect_diagnostics(settings: dict[str, Any]) -> RuntimeDiagnosticsReport:
    return collect_runtime_diagnostics(
        ffmpeg_exe=str(settings.get("ffmpeg_exe") or ""),
        ffprobe_exe=str(settings.get("ffprobe_exe") or ""),
    )


DESCRIPTOR = VideoProviderDescriptor(
    provider_id=PROVIDER_ID,
    label="FFmpeg local",
    description="Use local ffmpeg and ffprobe executables from PATH, environment variables, or video/local_models/ffmpeg_local.",
    render_sidebar=render_sidebar,
    aliases=("ffmpeg", "local ffmpeg", "ffmpeg-local"),
    sort_order=10,
    collect_runtime_diagnostics=collect_diagnostics,
)
