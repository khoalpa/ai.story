from __future__ import annotations

from .main_panel import render_story_main_panel
from .settings import get_story_settings
from .state import ensure_session_defaults


def render_story_workspace(*, embedded: bool = False) -> None:
    ensure_session_defaults()
    settings = get_story_settings()
    render_story_main_panel(settings, embedded=embedded)


def render_story_studio(*args, **kwargs):
    return render_story_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_story_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_story_studio(*args, **kwargs)


def main(_args=None) -> None:
    render_story_workspace()
