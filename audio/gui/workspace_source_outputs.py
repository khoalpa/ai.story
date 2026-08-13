from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]
AUDIO_LAST_OUTPUT_KEY = "audio_last_output"
AUDIO_LAST_SRT_OUTPUT_KEY = "audio_last_srt_output"


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


def workspace_source_outputs(state: SessionState | None = None) -> WorkspaceSourceOutputs:
    session = state if state is not None else cast(SessionState, st.session_state)
    session.setdefault(AUDIO_LAST_OUTPUT_KEY, "")
    session.setdefault(AUDIO_LAST_SRT_OUTPUT_KEY, "")
    return WorkspaceSourceOutputs(session)
