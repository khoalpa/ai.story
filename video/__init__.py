from __future__ import annotations

"""Public API for the video package."""

__version__ = "0.1.0"

from video.app_api import RenderVideoRequest, execute_render_request

__all__ = ["RenderVideoRequest", "execute_render_request", "__version__"]
