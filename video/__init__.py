from __future__ import annotations

"""Public API for the video package."""

__version__ = "0.1.0"

__all__ = ["RenderVideoRequest", "execute_render_request", "__version__"]


def __getattr__(name: str):
    if name in {"RenderVideoRequest", "execute_render_request"}:
        from video import app_api

        return getattr(app_api, name)
    raise AttributeError(name)
