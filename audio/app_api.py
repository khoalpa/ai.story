"""Stable integration surface for the standalone Audio application."""
from __future__ import annotations

from typing import Any

from audio.render_audio_app import (
    RenderAudioAppRequest,
    RenderAudioAppResult,
    create_app_request_from_args,
    create_default_app_request,
    run_render_audio_app,
    validate_only_script,
)


def render_audio_workspace(*, embedded: bool = False) -> None:
    """Render Audio's GUI without importing Streamlit for non-GUI callers."""
    from audio.gui.app import render_audio_workspace as render

    render(embedded=embedded)


def render_audio_studio(*args: Any, **kwargs: Any) -> None:
    """Backward-compatible name for embedded integrations."""
    kwargs.setdefault("embedded", True)
    render_audio_workspace(*args, **kwargs)


def validate_request(request: RenderAudioAppRequest) -> None:
    if not isinstance(request, RenderAudioAppRequest):
        raise TypeError("request must be RenderAudioAppRequest")
    if not request.input_path:
        raise ValueError("input_path is required")


def execute_request(
    request: RenderAudioAppRequest, *, ffmpeg_exe: str, ffprobe_exe: str
) -> RenderAudioAppResult:
    validate_request(request)
    return run_render_audio_app(request, ffmpeg_exe=ffmpeg_exe, ffprobe_exe=ffprobe_exe)


__all__ = [
    "RenderAudioAppRequest",
    "RenderAudioAppResult",
    "create_app_request_from_args",
    "create_default_app_request",
    "execute_request",
    "render_audio_studio",
    "render_audio_workspace",
    "run_render_audio_app",
    "validate_only_script",
    "validate_request",
]
