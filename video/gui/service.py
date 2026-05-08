from __future__ import annotations

"""Compatibility layer for GUI callers.

The shared render contract now lives in render_video.app_api so GUI and CLI use
the same request model and execution path.
"""

from video.app_api import RenderVideoRequest, execute_render_request


def run_video_job(request: RenderVideoRequest, progress_callback=None) -> dict[str, str]:
    return execute_render_request(request, progress_callback=progress_callback)
