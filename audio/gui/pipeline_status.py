from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping

from audio.gui.lock_flags import workspace_lock_flags
from audio.gui.workspace_handoff import workspace_handoff_state
from audio.gui.workspace_navigation import workspace_navigation_state

SessionState = MutableMapping[str, Any]


@dataclass(frozen=True)
class PipelineStatusSnapshot:
    story: str
    audio: str
    image: str
    video: str

    def as_dict(self) -> dict[str, str]:
        return {
            "story": self.story,
            "audio": self.audio,
            "image": self.image,
            "video": self.video,
        }



def compute_pipeline_status(state: SessionState) -> PipelineStatusSnapshot:
    handoff = workspace_handoff_state(state)
    navigation = workspace_navigation_state(state)
    locks = workspace_lock_flags(state)

    story_status = "idle"
    if handoff.story_plain_script_text or handoff.story_image_handoff_dir:
        story_status = "ready"
    if navigation.active_app in {"Audio", "Image"} and (locks.audio_to_story or locks.image_to_story):
        story_status = "sent"

    audio_status = "idle"
    if handoff.audio_output_path:
        audio_status = "ready"
    if navigation.active_app == "Video" and locks.video_to_audio:
        audio_status = "sent"

    image_status = "idle"
    if handoff.image_cover_path or handoff.image_scenes_dir:
        image_status = "ready"
    if navigation.active_app == "Video" and locks.video_to_image:
        image_status = "sent"

    video_status = "rendered" if handoff.last_video_output else "idle"

    return PipelineStatusSnapshot(
        story=story_status,
        audio=audio_status,
        image=image_status,
        video=video_status,
    )
