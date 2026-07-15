"""Stable integration surface for the standalone Story application.

Consumers such as :mod:`studio` should import this module instead of reaching
into ``story.gui`` or implementation services directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GenerateStoryRequest:
    argv: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GenerateStoryResult:
    exit_code: int


def validate_request(request: GenerateStoryRequest) -> None:
    if not isinstance(request, GenerateStoryRequest):
        raise TypeError("request must be GenerateStoryRequest")


def execute_request(request: GenerateStoryRequest) -> GenerateStoryResult:
    validate_request(request)
    return GenerateStoryResult(exit_code=main(request.argv))


def render_story_workspace(*, embedded: bool = False) -> None:
    """Render Story's GUI without importing Streamlit for non-GUI callers."""
    from story.gui.app import render_story_workspace as render

    render(embedded=embedded)


def render_story_studio(*args: Any, **kwargs: Any) -> None:
    """Backward-compatible name for embedded integrations."""
    kwargs.setdefault("embedded", True)
    render_story_workspace(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    """Run the standalone Story command-line application."""
    from story.generate_script import main as run

    return run(argv)


__all__ = [
    "GenerateStoryRequest", "GenerateStoryResult", "execute_request", "main",
    "render_story_studio", "render_story_workspace", "validate_request",
]
