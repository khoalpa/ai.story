from __future__ import annotations


def main() -> None:
    from .app import main as _main
    _main()


def render_video_workspace(*args, **kwargs):
    from .app import render_video_workspace as _render_video_workspace
    return _render_video_workspace(*args, **kwargs)


def render_video_studio(*args, **kwargs):
    return render_video_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_video_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_video_studio(*args, **kwargs)


__all__ = ["main", "render_video_workspace", "render_video_studio", "render_workspace", "render_studio"]
