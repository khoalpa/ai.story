from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]

WORKSPACE_LAST_STORY_OUTPUT_KEY = "workspace_last_story_output"
WORKSPACE_LAST_AUDIO_OUTPUT_KEY = "workspace_last_audio_output"
WORKSPACE_LAST_IMAGE_OUTPUT_KEY = "workspace_last_image_output"
WORKSPACE_LAST_VIDEO_OUTPUT_KEY = "workspace_last_video_output"
WORKSPACE_STORY_PLAIN_SCRIPT_TEXT_KEY = "workspace_story_plain_script_text"
WORKSPACE_STORY_IMAGE_HANDOFF_DIR_KEY = "workspace_story_image_handoff_dir"
WORKSPACE_STORY_VIDEO_HANDOFF_DIR_KEY = "workspace_story_video_handoff_dir"
WORKSPACE_AUDIO_OUTPUT_PATH_KEY = "workspace_audio_output_path"
WORKSPACE_AUDIO_SRT_PATH_KEY = "workspace_audio_srt_path"
WORKSPACE_IMAGE_COVER_PATH_KEY = "workspace_image_cover_path"
WORKSPACE_IMAGE_SCENES_DIR_KEY = "workspace_image_scenes_dir"
WORKSPACE_IMAGE_MANIFEST_PATH_KEY = "workspace_image_manifest_path"


def _get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return cast(SessionState, st.session_state)


def get_workspace_text(key: str, default: str = "", *, state: SessionState | None = None) -> str:
    session = _get_session_state(state)
    return str(session.get(key) or default)


@dataclass
class WorkspaceHandoffState:
    state: SessionState

    @property
    def last_story_output(self) -> str:
        return get_workspace_text(WORKSPACE_LAST_STORY_OUTPUT_KEY, state=self.state)

    @last_story_output.setter
    def last_story_output(self, value: str) -> None:
        self.state[WORKSPACE_LAST_STORY_OUTPUT_KEY] = value or ""

    @property
    def last_audio_output(self) -> str:
        return get_workspace_text(WORKSPACE_LAST_AUDIO_OUTPUT_KEY, state=self.state)

    @last_audio_output.setter
    def last_audio_output(self, value: str) -> None:
        self.state[WORKSPACE_LAST_AUDIO_OUTPUT_KEY] = value or ""

    @property
    def last_image_output(self) -> str:
        return get_workspace_text(WORKSPACE_LAST_IMAGE_OUTPUT_KEY, state=self.state)

    @last_image_output.setter
    def last_image_output(self, value: str) -> None:
        self.state[WORKSPACE_LAST_IMAGE_OUTPUT_KEY] = value or ""

    @property
    def last_video_output(self) -> str:
        return get_workspace_text(WORKSPACE_LAST_VIDEO_OUTPUT_KEY, state=self.state)

    @last_video_output.setter
    def last_video_output(self, value: str) -> None:
        self.state[WORKSPACE_LAST_VIDEO_OUTPUT_KEY] = value or ""

    @property
    def story_plain_script_text(self) -> str:
        return get_workspace_text(WORKSPACE_STORY_PLAIN_SCRIPT_TEXT_KEY, state=self.state)

    @story_plain_script_text.setter
    def story_plain_script_text(self, value: str) -> None:
        self.state[WORKSPACE_STORY_PLAIN_SCRIPT_TEXT_KEY] = value or ""

    @property
    def story_image_handoff_dir(self) -> str:
        return get_workspace_text(WORKSPACE_STORY_IMAGE_HANDOFF_DIR_KEY, state=self.state).strip()

    @story_image_handoff_dir.setter
    def story_image_handoff_dir(self, value: str) -> None:
        self.state[WORKSPACE_STORY_IMAGE_HANDOFF_DIR_KEY] = (value or "").strip()

    @property
    def story_video_handoff_dir(self) -> str:
        return get_workspace_text(WORKSPACE_STORY_VIDEO_HANDOFF_DIR_KEY, state=self.state).strip()

    @story_video_handoff_dir.setter
    def story_video_handoff_dir(self, value: str) -> None:
        self.state[WORKSPACE_STORY_VIDEO_HANDOFF_DIR_KEY] = (value or "").strip()

    @property
    def audio_output_path(self) -> str:
        return get_workspace_text(WORKSPACE_AUDIO_OUTPUT_PATH_KEY, state=self.state).strip()

    @audio_output_path.setter
    def audio_output_path(self, value: str) -> None:
        self.state[WORKSPACE_AUDIO_OUTPUT_PATH_KEY] = (value or "").strip()

    @property
    def audio_srt_path(self) -> str:
        return get_workspace_text(WORKSPACE_AUDIO_SRT_PATH_KEY, state=self.state).strip()

    @audio_srt_path.setter
    def audio_srt_path(self, value: str) -> None:
        self.state[WORKSPACE_AUDIO_SRT_PATH_KEY] = (value or "").strip()

    @property
    def image_cover_path(self) -> str:
        return get_workspace_text(WORKSPACE_IMAGE_COVER_PATH_KEY, state=self.state).strip()

    @image_cover_path.setter
    def image_cover_path(self, value: str) -> None:
        self.state[WORKSPACE_IMAGE_COVER_PATH_KEY] = (value or "").strip()

    @property
    def image_scenes_dir(self) -> str:
        return get_workspace_text(WORKSPACE_IMAGE_SCENES_DIR_KEY, state=self.state).strip()

    @image_scenes_dir.setter
    def image_scenes_dir(self, value: str) -> None:
        self.state[WORKSPACE_IMAGE_SCENES_DIR_KEY] = (value or "").strip()

    @property
    def image_manifest_path(self) -> str:
        return get_workspace_text(WORKSPACE_IMAGE_MANIFEST_PATH_KEY, state=self.state).strip()

    @image_manifest_path.setter
    def image_manifest_path(self, value: str) -> None:
        self.state[WORKSPACE_IMAGE_MANIFEST_PATH_KEY] = (value or "").strip()


def workspace_handoff_state(state: SessionState | None = None) -> WorkspaceHandoffState:
    return WorkspaceHandoffState(_get_session_state(state))
