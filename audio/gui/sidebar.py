from __future__ import annotations

from .config_bundle import GuiConfigBundle
from .settings import render_settings_sidebar


def render_sidebar() -> GuiConfigBundle:
    return render_settings_sidebar()


__all__ = ["render_settings_sidebar", "render_sidebar"]

