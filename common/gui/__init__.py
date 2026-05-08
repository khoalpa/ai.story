"""Shared GUI helpers with lazy imports to keep streamlit optional at import time."""

from __future__ import annotations


def render_workspace_shell(*args, **kwargs):
    from .shell import render_workspace_shell as _render_workspace_shell
    return _render_workspace_shell(*args, **kwargs)


def render_project_tools_workspace(*args, **kwargs):
    from .project_tools import render_project_tools_workspace as _render_project_tools_workspace
    return _render_project_tools_workspace(*args, **kwargs)


def ensure_workspace_shell_state(*args, **kwargs):
    from .state import ensure_workspace_shell_state as _ensure_workspace_shell_state
    return _ensure_workspace_shell_state(*args, **kwargs)


def render_studio_shell(*args, **kwargs):
    return render_workspace_shell(*args, **kwargs)


def ensure_studio_shell_state(*args, **kwargs):
    return ensure_workspace_shell_state(*args, **kwargs)


__all__ = [
    "render_workspace_shell",
    "render_project_tools_workspace",
    "ensure_workspace_shell_state",
    "render_studio_shell",
    "ensure_studio_shell_state",
]
