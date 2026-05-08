from __future__ import annotations


def main() -> None:
    from .app import main as _main
    _main()


def render_image_workspace(*args, **kwargs):
    from .app import render_image_workspace as _render_image_workspace
    return _render_image_workspace(*args, **kwargs)


def render_image_studio(*args, **kwargs):
    return render_image_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_image_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_image_studio(*args, **kwargs)


__all__ = ["main", "render_image_workspace", "render_image_studio", "render_workspace", "render_studio"]

