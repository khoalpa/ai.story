from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping

SessionState = MutableMapping[str, Any]

AUDIO_LOCK_TO_STORY_HANDOFF_KEY = "audio_lock_to_story_handoff"
IMAGE_LOCK_TO_STORY_HANDOFF_KEY = "image_lock_to_story_handoff"
VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY = "video_lock_to_audio_handoff"
VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY = "video_lock_to_image_handoff"

LOCK_FLAG_DEFAULTS: dict[str, bool] = {
    AUDIO_LOCK_TO_STORY_HANDOFF_KEY: False,
    IMAGE_LOCK_TO_STORY_HANDOFF_KEY: True,
    VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY: False,
    VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY: True,
}


@dataclass
class WorkspaceLockFlags:
    state: SessionState

    @property
    def audio_to_story(self) -> bool:
        return bool(self.state.get(AUDIO_LOCK_TO_STORY_HANDOFF_KEY, LOCK_FLAG_DEFAULTS[AUDIO_LOCK_TO_STORY_HANDOFF_KEY]))

    @audio_to_story.setter
    def audio_to_story(self, value: bool) -> None:
        self.state[AUDIO_LOCK_TO_STORY_HANDOFF_KEY] = bool(value)

    @property
    def image_to_story(self) -> bool:
        return bool(self.state.get(IMAGE_LOCK_TO_STORY_HANDOFF_KEY, LOCK_FLAG_DEFAULTS[IMAGE_LOCK_TO_STORY_HANDOFF_KEY]))

    @image_to_story.setter
    def image_to_story(self, value: bool) -> None:
        self.state[IMAGE_LOCK_TO_STORY_HANDOFF_KEY] = bool(value)

    @property
    def video_to_audio(self) -> bool:
        return bool(self.state.get(VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY, LOCK_FLAG_DEFAULTS[VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY]))

    @video_to_audio.setter
    def video_to_audio(self, value: bool) -> None:
        self.state[VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY] = bool(value)

    @property
    def video_to_image(self) -> bool:
        return bool(self.state.get(VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY, LOCK_FLAG_DEFAULTS[VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY]))

    @video_to_image.setter
    def video_to_image(self, value: bool) -> None:
        self.state[VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY] = bool(value)



def workspace_lock_flags(state: SessionState) -> WorkspaceLockFlags:
    return WorkspaceLockFlags(state)
