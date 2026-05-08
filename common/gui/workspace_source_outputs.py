from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]

STORY_LAST_PLAIN_SCRIPT_PATH_KEY = "story_last_plain_script_path"
AUDIO_LAST_OUTPUT_KEY = "audio_last_output"
AUDIO_LAST_SRT_OUTPUT_KEY = "audio_last_srt_output"
IMAGE_LAST_COVER_OUTPUT_KEY = "image_last_cover_output"
IMAGE_LAST_SCENES_DIR_KEY = "image_last_scenes_dir"
VIDEO_LAST_OUTPUT_KEY = "video_last_output"

WORKSPACE_SOURCE_OUTPUT_DEFAULTS: dict[str, str] = {
    STORY_LAST_PLAIN_SCRIPT_PATH_KEY: "",
    AUDIO_LAST_OUTPUT_KEY: "",
    AUDIO_LAST_SRT_OUTPUT_KEY: "",
    IMAGE_LAST_COVER_OUTPUT_KEY: "",
    IMAGE_LAST_SCENES_DIR_KEY: "",
    VIDEO_LAST_OUTPUT_KEY: "",
}


def _get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return cast(SessionState, st.session_state)


def get_source_output_text(key: str, default: str = "", *, state: SessionState | None = None) -> str:
    session = _get_session_state(state)
    return str(session.get(key) or default)


@dataclass
class WorkspaceSourceOutputs:
    state: SessionState

    @property
    def story_plain_script_path(self) -> str:
        return get_source_output_text(STORY_LAST_PLAIN_SCRIPT_PATH_KEY, state=self.state).strip()

    @story_plain_script_path.setter
    def story_plain_script_path(self, value: str) -> None:
        self.state[STORY_LAST_PLAIN_SCRIPT_PATH_KEY] = (value or "").strip()

    @property
    def audio_output(self) -> str:
        return get_source_output_text(AUDIO_LAST_OUTPUT_KEY, state=self.state).strip()

    @audio_output.setter
    def audio_output(self, value: str) -> None:
        self.state[AUDIO_LAST_OUTPUT_KEY] = (value or "").strip()

    @property
    def audio_srt_output(self) -> str:
        return get_source_output_text(AUDIO_LAST_SRT_OUTPUT_KEY, state=self.state).strip()

    @audio_srt_output.setter
    def audio_srt_output(self, value: str) -> None:
        self.state[AUDIO_LAST_SRT_OUTPUT_KEY] = (value or "").strip()

    @property
    def image_cover_output(self) -> str:
        return get_source_output_text(IMAGE_LAST_COVER_OUTPUT_KEY, state=self.state).strip()

    @image_cover_output.setter
    def image_cover_output(self, value: str) -> None:
        self.state[IMAGE_LAST_COVER_OUTPUT_KEY] = (value or "").strip()

    @property
    def image_scenes_dir(self) -> str:
        return get_source_output_text(IMAGE_LAST_SCENES_DIR_KEY, state=self.state).strip()

    @image_scenes_dir.setter
    def image_scenes_dir(self, value: str) -> None:
        self.state[IMAGE_LAST_SCENES_DIR_KEY] = (value or "").strip()

    @property
    def video_output(self) -> str:
        return get_source_output_text(VIDEO_LAST_OUTPUT_KEY, state=self.state).strip()

    @video_output.setter
    def video_output(self, value: str) -> None:
        self.state[VIDEO_LAST_OUTPUT_KEY] = (value or "").strip()



def workspace_source_outputs(state: SessionState | None = None) -> WorkspaceSourceOutputs:
    session = _get_session_state(state)
    for key, value in WORKSPACE_SOURCE_OUTPUT_DEFAULTS.items():
        session.setdefault(key, value)
    return WorkspaceSourceOutputs(session)
