from __future__ import annotations

import pytest

from studio.navigation import navigate_to, pipeline_step_for_workspace
from studio.ui_components import PIPELINE_STEPS


def test_navigation_keeps_internal_workspace_keys_and_deep_links() -> None:
    state: dict[str, object] = {}
    navigate_to(state, "Story Studio", story_section="Tài nguyên")
    assert state["studio_workspace"] == "Story Studio"
    assert state["story_studio_section"] == "Tài nguyên"

    navigate_to(state, "Video Studio", view="inputs")
    assert state["studio_workspace"] == "Video Studio"
    assert state["workspace_video_target_view"] == "inputs"
    assert state["video_embedded_view_selector"] == "inputs"


def test_navigation_rejects_unknown_workspace() -> None:
    with pytest.raises(ValueError, match="Không gian làm việc"):
        navigate_to({}, "Unknown")


def test_pipeline_has_five_stable_steps() -> None:
    assert PIPELINE_STEPS == ("Nội dung", "Audio", "Bàn giao", "Video", "Hoàn tất")
    assert pipeline_step_for_workspace("Story Studio", {}) == 1
    assert pipeline_step_for_workspace("Audio Studio", {}) == 2
    assert pipeline_step_for_workspace("Video Studio", {}) == 4
    assert pipeline_step_for_workspace("Overview", {"video_last_output": "final.mp4"}) == 5
