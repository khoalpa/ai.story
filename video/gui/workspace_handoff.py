from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]
WORKSPACE_AUDIO_OUTPUT_PATH_KEY = "workspace_audio_output_path"
WORKSPACE_AUDIO_SRT_PATH_KEY = "workspace_audio_srt_path"
WORKSPACE_LAST_AUDIO_OUTPUT_KEY = "workspace_last_audio_output"
WORKSPACE_LAST_VIDEO_OUTPUT_KEY = "workspace_last_video_output"


@dataclass
class WorkspaceHandoffState:
    state: SessionState

    @property
    def audio_output_path(self) -> str:
        return str(self.state.get(WORKSPACE_AUDIO_OUTPUT_PATH_KEY) or "").strip()

    @audio_output_path.setter
    def audio_output_path(self, value: str) -> None:
        self.state[WORKSPACE_AUDIO_OUTPUT_PATH_KEY] = (value or "").strip()

    @property
    def audio_srt_path(self) -> str:
        return str(self.state.get(WORKSPACE_AUDIO_SRT_PATH_KEY) or "").strip()

    @audio_srt_path.setter
    def audio_srt_path(self, value: str) -> None:
        self.state[WORKSPACE_AUDIO_SRT_PATH_KEY] = (value or "").strip()

    @property
    def last_audio_output(self) -> str:
        return str(self.state.get(WORKSPACE_LAST_AUDIO_OUTPUT_KEY) or "").strip()

    @last_audio_output.setter
    def last_audio_output(self, value: str) -> None:
        self.state[WORKSPACE_LAST_AUDIO_OUTPUT_KEY] = (value or "").strip()

    @property
    def last_video_output(self) -> str:
        return str(self.state.get(WORKSPACE_LAST_VIDEO_OUTPUT_KEY) or "").strip()

    @last_video_output.setter
    def last_video_output(self, value: str) -> None:
        self.state[WORKSPACE_LAST_VIDEO_OUTPUT_KEY] = (value or "").strip()


def workspace_handoff_state(state: SessionState | None = None) -> WorkspaceHandoffState:
    return WorkspaceHandoffState(state if state is not None else cast(SessionState, st.session_state))
