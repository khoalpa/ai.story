"""Story GUI package with lazy imports to keep streamlit optional at import time."""

from __future__ import annotations


def main() -> None:
    from .app import main as _main
    _main()


def render_story_workspace(*args, **kwargs):
    from .app import render_story_workspace as _render_story_workspace
    return _render_story_workspace(*args, **kwargs)


def render_story_studio(*args, **kwargs):
    return render_story_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_story_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_story_studio(*args, **kwargs)


__all__ = ["main", "render_story_workspace", "render_story_studio", "render_workspace", "render_studio"]
