from __future__ import annotations

from typing import Any

from .settings import render_settings_sidebar


def render_sidebar() -> dict[str, Any]:
    return render_settings_sidebar()


__all__ = ["render_settings_sidebar", "render_sidebar"]


