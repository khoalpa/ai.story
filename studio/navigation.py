"""Shared navigation state for the unified Studio shell."""
from __future__ import annotations

from typing import Any, MutableMapping

WORKSPACE_KEYS = (
    "Overview",
    "Story Studio",
    "Audio Studio",
    "Video Studio",
    "Prompt Info",
)


def navigate_to(
    state: MutableMapping[str, Any],
    workspace: str,
    *,
    story_section: str | None = None,
    view: str | None = None,
) -> None:
    """Select a top-level workspace and an optional durable deep-link target."""
    if workspace not in WORKSPACE_KEYS:
        raise ValueError(f"Không gian làm việc không hợp lệ: {workspace}")
    state["studio_workspace"] = workspace
    if story_section:
        state["story_studio_section"] = story_section
    if view and workspace == "Audio Studio":
        state["workspace_audio_target_view"] = view
        state["audio_embedded_view_selector"] = view
    elif view and workspace == "Video Studio":
        state["workspace_video_target_view"] = view
        state["video_embedded_view_selector"] = view


def pipeline_step_for_workspace(workspace: str, state: MutableMapping[str, Any]) -> int:
    """Return the most useful active production step for the current workspace."""
    if workspace == "Story Studio":
        return 1
    if workspace == "Audio Studio":
        return 2
    if workspace == "Video Studio":
        return 4
    if workspace == "Overview":
        if state.get("video_last_output"):
            return 5
        if state.get("workspace_audio_output_path") or state.get("video_audio_handoff_manifest"):
            return 3
        if state.get("last_result_summary") or state.get("audio_last_output"):
            return 2
    return 1


__all__ = ["WORKSPACE_KEYS", "navigate_to", "pipeline_step_for_workspace"]
