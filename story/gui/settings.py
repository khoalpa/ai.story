from __future__ import annotations

from .sidebar import render_settings_sidebar


def get_story_settings():
    return render_settings_sidebar()


def get_settings():
    return get_story_settings()


def render_settings():
    return get_story_settings()


def render_sidebar():
    return render_settings_sidebar()
