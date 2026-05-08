"""GUI package for Render Audio."""

from __future__ import annotations


def main() -> None:
    from .app import main as _main
    _main()


def render_audio_workspace(*args, **kwargs):
    from .app import render_audio_workspace as _render_audio_workspace
    return _render_audio_workspace(*args, **kwargs)


def render_audio_studio(*args, **kwargs):
    return render_audio_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_audio_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_audio_studio(*args, **kwargs)


__all__ = ["main", "render_audio_workspace", "render_audio_studio", "render_workspace", "render_studio"]
