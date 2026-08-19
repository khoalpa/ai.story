from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]

PLAIN_SCRIPT_TEXT_KEY = "plain_script_text"
CANONICAL_JSON_TEXT_KEY = "canonical_json_text"
RAW_TEXT_KEY = "raw_text"
LAST_PLAIN_SCRIPT_KEY = "last_plain_script"
LAST_PREVIEW_SEGMENTS_KEY = "last_preview_segments"
LAST_RESULT_SUMMARY_KEY = "last_result_summary"
LAST_EVENT_LOG_KEY = "last_event_log"
WORKSPACE_TITLE_KEY = "workspace_title"
BATCH_MANIFEST_TEXT_KEY = "batch_manifest_text"
PENDING_PLAIN_SCRIPT_KEY = "pending_plain_script"
PENDING_RUN_PLAIN_TEXT_KEY = "pending_run_plain_text"
RUN_PLAIN_TEXT_KEY = "run_plain_text"
PREVIEW_TTS_TEXT_KEY = "preview_tts_text"
PREVIEW_TTS_LANG_KEY = "preview_tts_lang"
PREVIEW_TTS_ROLE_KEY = "preview_tts_role"
PREVIEW_TTS_PROVIDER_KEY = "preview_tts_provider"
LAST_PREVIEW_AUDIO_PATH_KEY = "last_preview_audio_path"
LAST_PREVIEW_AUDIO_ERROR_KEY = "last_preview_audio_error"
AUDIO_LAST_OUTPUT_KEY = "audio_last_output"
AUDIO_LAST_SRT_OUTPUT_KEY = "audio_last_srt_output"
PLAIN_SCRIPT_EDITOR_KEY = "plain_script_editor"
CANONICAL_EDITOR_KEY = "canonical_editor"
RAW_EDITOR_KEY = "raw_editor"

AUDIO_EDITOR_DEFAULTS: dict[str, object] = {
    PLAIN_SCRIPT_TEXT_KEY: "",
    CANONICAL_JSON_TEXT_KEY: "",
    RAW_TEXT_KEY: "",
    PLAIN_SCRIPT_EDITOR_KEY: "",
    CANONICAL_EDITOR_KEY: "",
    RAW_EDITOR_KEY: "",
    BATCH_MANIFEST_TEXT_KEY: "",
    WORKSPACE_TITLE_KEY: "",
}

AUDIO_RUN_DEFAULTS: dict[str, object] = {
    LAST_PLAIN_SCRIPT_KEY: "",
    PENDING_PLAIN_SCRIPT_KEY: None,
    PENDING_RUN_PLAIN_TEXT_KEY: None,
    RUN_PLAIN_TEXT_KEY: "",
    LAST_RESULT_SUMMARY_KEY: None,
    LAST_EVENT_LOG_KEY: [],
    AUDIO_LAST_OUTPUT_KEY: "",
    AUDIO_LAST_SRT_OUTPUT_KEY: "",
}

AUDIO_PREVIEW_DEFAULTS: dict[str, object] = {
    LAST_PREVIEW_SEGMENTS_KEY: [],
    PREVIEW_TTS_TEXT_KEY: "Xin chào, đây là câu nghe thử giọng đọc.",
    PREVIEW_TTS_LANG_KEY: "vi",
    PREVIEW_TTS_ROLE_KEY: "narrator",
    PREVIEW_TTS_PROVIDER_KEY: "",
    LAST_PREVIEW_AUDIO_PATH_KEY: "",
    LAST_PREVIEW_AUDIO_ERROR_KEY: "",
}

VOICE_NARRATOR_SPEED_KEY = "voice_narrator_speed"
VOICE_FEMALE_SPEED_KEY = "voice_female_speed"
VOICE_MALE_SPEED_KEY = "voice_male_speed"
VOICE_EN_NARRATOR_SPEED_KEY = "voice_en_narrator_speed"
VOICE_EN_FEMALE_SPEED_KEY = "voice_en_female_speed"
VOICE_EN_MALE_SPEED_KEY = "voice_en_male_speed"

VOICE_SPEED_DEFAULTS: dict[str, object] = {
    VOICE_NARRATOR_SPEED_KEY: 20,
    VOICE_FEMALE_SPEED_KEY: 20,
    VOICE_MALE_SPEED_KEY: 20,
    VOICE_EN_NARRATOR_SPEED_KEY: 20,
    VOICE_EN_FEMALE_SPEED_KEY: 20,
    VOICE_EN_MALE_SPEED_KEY: 20,
}

AUDIO_DEFAULTS: dict[str, object] = {
    **AUDIO_EDITOR_DEFAULTS,
    **AUDIO_RUN_DEFAULTS,
    **AUDIO_PREVIEW_DEFAULTS,
    **VOICE_SPEED_DEFAULTS,
}


def _get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return cast(SessionState, st.session_state)


def ensure_session_defaults(state: SessionState | None = None) -> None:
    session = _get_session_state(state)

    for key, value in AUDIO_DEFAULTS.items():
        session.setdefault(key, value)


@dataclass
class AudioEditorState:
    state: SessionState

    @property
    def plain_script_text(self) -> str:
        return str(self.state.get(PLAIN_SCRIPT_TEXT_KEY) or "")

    @plain_script_text.setter
    def plain_script_text(self, value: str) -> None:
        self.state[PLAIN_SCRIPT_TEXT_KEY] = value or ""

    @property
    def plain_script_editor(self) -> str:
        return str(self.state.get(PLAIN_SCRIPT_EDITOR_KEY) or "")

    @plain_script_editor.setter
    def plain_script_editor(self, value: str) -> None:
        self.state[PLAIN_SCRIPT_EDITOR_KEY] = value or ""


@dataclass
class AudioRunState:
    state: SessionState

    @property
    def run_plain_text(self) -> str:
        return str(self.state.get(RUN_PLAIN_TEXT_KEY) or "")

    @run_plain_text.setter
    def run_plain_text(self, value: str) -> None:
        self.state[RUN_PLAIN_TEXT_KEY] = value or ""

    @property
    def last_plain_script(self) -> str:
        return str(self.state.get(LAST_PLAIN_SCRIPT_KEY) or "")

    @last_plain_script.setter
    def last_plain_script(self, value: str) -> None:
        self.state[LAST_PLAIN_SCRIPT_KEY] = value or ""

    @property
    def pending_plain_script(self) -> Any:
        return self.state.get(PENDING_PLAIN_SCRIPT_KEY)

    @pending_plain_script.setter
    def pending_plain_script(self, value: Any) -> None:
        self.state[PENDING_PLAIN_SCRIPT_KEY] = value

    @property
    def last_output(self) -> str:
        return str(self.state.get(AUDIO_LAST_OUTPUT_KEY) or "")

    @last_output.setter
    def last_output(self, value: str) -> None:
        self.state[AUDIO_LAST_OUTPUT_KEY] = value or ""

    @property
    def last_srt_output(self) -> str:
        return str(self.state.get(AUDIO_LAST_SRT_OUTPUT_KEY) or "")

    @last_srt_output.setter
    def last_srt_output(self, value: str) -> None:
        self.state[AUDIO_LAST_SRT_OUTPUT_KEY] = value or ""


@dataclass
class AudioSession:
    state: SessionState

    @property
    def editor(self) -> AudioEditorState:
        return AudioEditorState(self.state)

    @property
    def run(self) -> AudioRunState:
        return AudioRunState(self.state)

    @property
    def plain_script_text(self) -> str:
        return self.editor.plain_script_text

    @plain_script_text.setter
    def plain_script_text(self, value: str) -> None:
        self.editor.plain_script_text = value

    @property
    def plain_script_editor(self) -> str:
        return self.editor.plain_script_editor

    @plain_script_editor.setter
    def plain_script_editor(self, value: str) -> None:
        self.editor.plain_script_editor = value

    @property
    def run_plain_text(self) -> str:
        return self.run.run_plain_text

    @run_plain_text.setter
    def run_plain_text(self, value: str) -> None:
        self.run.run_plain_text = value

    @property
    def last_plain_script(self) -> str:
        return self.run.last_plain_script

    @last_plain_script.setter
    def last_plain_script(self, value: str) -> None:
        self.run.last_plain_script = value

    @property
    def pending_plain_script(self) -> Any:
        return self.run.pending_plain_script

    @pending_plain_script.setter
    def pending_plain_script(self, value: Any) -> None:
        self.run.pending_plain_script = value

    @property
    def last_output(self) -> str:
        return self.run.last_output

    @last_output.setter
    def last_output(self, value: str) -> None:
        self.run.last_output = value

    @property
    def last_srt_output(self) -> str:
        return self.run.last_srt_output

    @last_srt_output.setter
    def last_srt_output(self, value: str) -> None:
        self.run.last_srt_output = value


def audio_session(state: SessionState | None = None) -> AudioSession:
    session = _get_session_state(state)
    ensure_session_defaults(session)
    return AudioSession(session)
