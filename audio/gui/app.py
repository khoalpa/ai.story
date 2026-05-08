from __future__ import annotations

from .main_panel import render_audio_main_panel
from .settings import get_audio_settings


def render_audio_workspace(*, embedded: bool = False) -> None:
    settings = get_audio_settings()
    render_audio_main_panel(settings, embedded=embedded)


def render_audio_studio(*args, **kwargs):
    return render_audio_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_audio_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_audio_studio(*args, **kwargs)


def main(_args=None) -> None:
    render_audio_workspace()
