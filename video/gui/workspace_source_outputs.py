from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]
AUDIO_LAST_OUTPUT_KEY = "audio_last_output"
AUDIO_LAST_SRT_OUTPUT_KEY = "audio_last_srt_output"
VIDEO_LAST_OUTPUT_KEY = "video_last_output"
WORKSPACE_SOURCE_OUTPUT_DEFAULTS = {
    AUDIO_LAST_OUTPUT_KEY: "",
    AUDIO_LAST_SRT_OUTPUT_KEY: "",
    VIDEO_LAST_OUTPUT_KEY: "",
}


@dataclass
class WorkspaceSourceOutputs:
    state: SessionState

    @property
    def audio_output(self) -> str:
        return str(self.state.get(AUDIO_LAST_OUTPUT_KEY) or "").strip()

    @audio_output.setter
    def audio_output(self, value: str) -> None:
        self.state[AUDIO_LAST_OUTPUT_KEY] = (value or "").strip()

    @property
    def audio_srt_output(self) -> str:
        return str(self.state.get(AUDIO_LAST_SRT_OUTPUT_KEY) or "").strip()

    @audio_srt_output.setter
    def audio_srt_output(self, value: str) -> None:
        self.state[AUDIO_LAST_SRT_OUTPUT_KEY] = (value or "").strip()

    @property
    def video_output(self) -> str:
        return str(self.state.get(VIDEO_LAST_OUTPUT_KEY) or "").strip()

    @video_output.setter
    def video_output(self, value: str) -> None:
        self.state[VIDEO_LAST_OUTPUT_KEY] = (value or "").strip()


def workspace_source_outputs(state: SessionState | None = None) -> WorkspaceSourceOutputs:
    session = state if state is not None else cast(SessionState, st.session_state)
    for key, value in WORKSPACE_SOURCE_OUTPUT_DEFAULTS.items():
        session.setdefault(key, value)
    return WorkspaceSourceOutputs(session)
