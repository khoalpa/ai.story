from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]

VIDEO_AUDIO_INPUT_KEY = "video_audio_input"
VIDEO_SUBTITLE_INPUT_KEY = "video_subtitle_input"
VIDEO_OUTPUT_INPUT_KEY = "video_output_input"
VIDEO_COVER_INPUT_KEY = "video_cover_input"
VIDEO_SCENES_INPUT_KEY = "video_scenes_input"
VIDEO_LAST_SUMMARY_KEY = "video_last_summary"
VIDEO_LAST_STDOUT_KEY = "video_last_stdout"
VIDEO_LAST_STDERR_KEY = "video_last_stderr"
VIDEO_LAST_ERROR_KEY = "video_last_error"
VIDEO_LAST_OUTPUT_KEY = "video_last_output"
VIDEO_RUN_HISTORY_KEY = "video_run_history"
WORKSPACE_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY = "workspace_video_last_auto_audio_input"
STUDIO_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY = "studio_video_last_auto_audio_input"
LEGACY_STUDIO_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY = STUDIO_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY
WORKSPACE_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY = "workspace_video_last_auto_subtitle_input"
STUDIO_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY = "studio_video_last_auto_subtitle_input"
LEGACY_STUDIO_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY = STUDIO_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY
WORKSPACE_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY = "workspace_video_last_auto_output_input"
STUDIO_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY = "studio_video_last_auto_output_input"
LEGACY_STUDIO_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY = STUDIO_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY
WORKSPACE_VIDEO_LAST_AUTO_COVER_INPUT_KEY = "workspace_video_last_auto_cover_input"
STUDIO_VIDEO_LAST_AUTO_COVER_INPUT_KEY = "studio_video_last_auto_cover_input"
LEGACY_STUDIO_VIDEO_LAST_AUTO_COVER_INPUT_KEY = STUDIO_VIDEO_LAST_AUTO_COVER_INPUT_KEY
WORKSPACE_VIDEO_LAST_AUTO_SCENES_INPUT_KEY = "workspace_video_last_auto_scenes_input"
STUDIO_VIDEO_LAST_AUTO_SCENES_INPUT_KEY = "studio_video_last_auto_scenes_input"
LEGACY_STUDIO_VIDEO_LAST_AUTO_SCENES_INPUT_KEY = STUDIO_VIDEO_LAST_AUTO_SCENES_INPUT_KEY
VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY = "video_lock_to_audio_handoff"
VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY = "video_lock_to_image_handoff"
VIDEO_LAST_RESULT_HISTORY_FILE_KEY = "video_last_result_history_file"
VIDEO_COVER_SOURCE_KEY = "video_cover_source"
VIDEO_SCENES_SOURCE_KEY = "video_scenes_source"
VIDEO_INPUT_COVER_PATH_KEY = "video_input_cover_path"
VIDEO_INPUT_SCENES_DIR_KEY = "video_input_scenes_dir"

VIDEO_INPUT_DEFAULTS: dict[str, object] = {
    VIDEO_AUDIO_INPUT_KEY: "output/story.mp3",
    VIDEO_SUBTITLE_INPUT_KEY: "",
    VIDEO_OUTPUT_INPUT_KEY: "output/story.mp4",
    VIDEO_COVER_INPUT_KEY: "",
    VIDEO_SCENES_INPUT_KEY: "",
    VIDEO_COVER_SOURCE_KEY: "handoff",
    VIDEO_SCENES_SOURCE_KEY: "handoff",
    VIDEO_INPUT_COVER_PATH_KEY: "output/default_cover.png",
    VIDEO_INPUT_SCENES_DIR_KEY: "output/scene_images",
}

VIDEO_RESULT_DEFAULTS: dict[str, object] = {
    VIDEO_LAST_SUMMARY_KEY: None,
    VIDEO_LAST_STDOUT_KEY: "",
    VIDEO_LAST_STDERR_KEY: "",
    VIDEO_LAST_ERROR_KEY: "",
    VIDEO_LAST_OUTPUT_KEY: "",
    VIDEO_RUN_HISTORY_KEY: [],
    VIDEO_LAST_RESULT_HISTORY_FILE_KEY: "",
}

VIDEO_AUTO_INPUT_DEFAULTS: dict[str, object] = {
    WORKSPACE_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY: "",
    WORKSPACE_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY: "",
    WORKSPACE_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY: "",
    WORKSPACE_VIDEO_LAST_AUTO_COVER_INPUT_KEY: "",
    WORKSPACE_VIDEO_LAST_AUTO_SCENES_INPUT_KEY: "",
}

VIDEO_HANDOFF_DEFAULTS: dict[str, object] = {
    VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY: False,
    VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY: True,
}

VIDEO_DEFAULTS: dict[str, object] = {
    **VIDEO_INPUT_DEFAULTS,
    **VIDEO_RESULT_DEFAULTS,
    **VIDEO_AUTO_INPUT_DEFAULTS,
    **VIDEO_HANDOFF_DEFAULTS,
}

LEGACY_AUTO_INPUT_PAIRS = [
    (LEGACY_STUDIO_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY, WORKSPACE_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY),
    (LEGACY_STUDIO_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY, WORKSPACE_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY),
    (LEGACY_STUDIO_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY, WORKSPACE_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY),
    (LEGACY_STUDIO_VIDEO_LAST_AUTO_COVER_INPUT_KEY, WORKSPACE_VIDEO_LAST_AUTO_COVER_INPUT_KEY),
    (LEGACY_STUDIO_VIDEO_LAST_AUTO_SCENES_INPUT_KEY, WORKSPACE_VIDEO_LAST_AUTO_SCENES_INPUT_KEY),
]


def _get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return cast(SessionState, st.session_state)


def ensure_session_defaults(state: SessionState | None = None) -> None:
    session = _get_session_state(state)
    for legacy_key, new_key in LEGACY_AUTO_INPUT_PAIRS:
        if legacy_key in session and new_key not in session:
            session[new_key] = session[legacy_key]
    for key, value in VIDEO_DEFAULTS.items():
        session.setdefault(key, value)
    for legacy_key, new_key in LEGACY_AUTO_INPUT_PAIRS:
        if new_key in session:
            session[legacy_key] = session[new_key]


@dataclass
class VideoInputsState:
    state: SessionState

    @property
    def audio_input(self) -> str:
        return str(self.state.get(VIDEO_AUDIO_INPUT_KEY) or "")

    @audio_input.setter
    def audio_input(self, value: str) -> None:
        self.state[VIDEO_AUDIO_INPUT_KEY] = value or ""

    @property
    def subtitle_input(self) -> str:
        return str(self.state.get(VIDEO_SUBTITLE_INPUT_KEY) or "")

    @subtitle_input.setter
    def subtitle_input(self, value: str) -> None:
        self.state[VIDEO_SUBTITLE_INPUT_KEY] = value or ""

    @property
    def output_input(self) -> str:
        return str(self.state.get(VIDEO_OUTPUT_INPUT_KEY) or "")

    @output_input.setter
    def output_input(self, value: str) -> None:
        self.state[VIDEO_OUTPUT_INPUT_KEY] = value or ""

    @property
    def cover_input(self) -> str:
        return str(self.state.get(VIDEO_COVER_INPUT_KEY) or "")

    @cover_input.setter
    def cover_input(self, value: str) -> None:
        self.state[VIDEO_COVER_INPUT_KEY] = value or ""

    @property
    def scenes_input(self) -> str:
        return str(self.state.get(VIDEO_SCENES_INPUT_KEY) or "")

    @scenes_input.setter
    def scenes_input(self, value: str) -> None:
        self.state[VIDEO_SCENES_INPUT_KEY] = value or ""


@dataclass
class VideoAutoInputsState:
    state: SessionState

    def _read(self, primary_key: str, legacy_key: str) -> str:
        return str(self.state.get(primary_key) or self.state.get(legacy_key) or "")

    def _write(self, primary_key: str, legacy_key: str, value: str) -> None:
        normalized = value or ""
        self.state[primary_key] = normalized
        self.state[legacy_key] = normalized

    @property
    def audio_input(self) -> str:
        return self._read(WORKSPACE_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY)

    @audio_input.setter
    def audio_input(self, value: str) -> None:
        self._write(WORKSPACE_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_AUDIO_INPUT_KEY, value)

    @property
    def subtitle_input(self) -> str:
        return self._read(WORKSPACE_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY)

    @subtitle_input.setter
    def subtitle_input(self, value: str) -> None:
        self._write(WORKSPACE_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_SUBTITLE_INPUT_KEY, value)

    @property
    def output_input(self) -> str:
        return self._read(WORKSPACE_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY)

    @output_input.setter
    def output_input(self, value: str) -> None:
        self._write(WORKSPACE_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_OUTPUT_INPUT_KEY, value)

    @property
    def cover_input(self) -> str:
        return self._read(WORKSPACE_VIDEO_LAST_AUTO_COVER_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_COVER_INPUT_KEY)

    @cover_input.setter
    def cover_input(self, value: str) -> None:
        self._write(WORKSPACE_VIDEO_LAST_AUTO_COVER_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_COVER_INPUT_KEY, value)

    @property
    def scenes_input(self) -> str:
        return self._read(WORKSPACE_VIDEO_LAST_AUTO_SCENES_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_SCENES_INPUT_KEY)

    @scenes_input.setter
    def scenes_input(self, value: str) -> None:
        self._write(WORKSPACE_VIDEO_LAST_AUTO_SCENES_INPUT_KEY, LEGACY_STUDIO_VIDEO_LAST_AUTO_SCENES_INPUT_KEY, value)


@dataclass
class VideoHandoffState:
    state: SessionState

    @property
    def lock_to_audio_handoff(self) -> bool:
        return bool(self.state.get(VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY, False))

    @lock_to_audio_handoff.setter
    def lock_to_audio_handoff(self, value: bool) -> None:
        self.state[VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY] = bool(value)

    @property
    def lock_to_image_handoff(self) -> bool:
        return bool(self.state.get(VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY, True))

    @lock_to_image_handoff.setter
    def lock_to_image_handoff(self, value: bool) -> None:
        self.state[VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY] = bool(value)


@dataclass
class VideoResultsState:
    state: SessionState

    @property
    def last_output(self) -> str:
        return str(self.state.get(VIDEO_LAST_OUTPUT_KEY) or "")

    @last_output.setter
    def last_output(self, value: str) -> None:
        self.state[VIDEO_LAST_OUTPUT_KEY] = value or ""


@dataclass
class VideoSession:
    state: SessionState

    @property
    def inputs(self) -> VideoInputsState:
        return VideoInputsState(self.state)

    @property
    def auto_inputs(self) -> VideoAutoInputsState:
        return VideoAutoInputsState(self.state)

    @property
    def handoff(self) -> VideoHandoffState:
        return VideoHandoffState(self.state)

    @property
    def results(self) -> VideoResultsState:
        return VideoResultsState(self.state)

    @property
    def audio_input(self) -> str:
        return self.inputs.audio_input

    @audio_input.setter
    def audio_input(self, value: str) -> None:
        self.inputs.audio_input = value

    @property
    def subtitle_input(self) -> str:
        return self.inputs.subtitle_input

    @subtitle_input.setter
    def subtitle_input(self, value: str) -> None:
        self.inputs.subtitle_input = value

    @property
    def output_input(self) -> str:
        return self.inputs.output_input

    @output_input.setter
    def output_input(self, value: str) -> None:
        self.inputs.output_input = value

    @property
    def cover_input(self) -> str:
        return self.inputs.cover_input

    @cover_input.setter
    def cover_input(self, value: str) -> None:
        self.inputs.cover_input = value

    @property
    def scenes_input(self) -> str:
        return self.inputs.scenes_input

    @scenes_input.setter
    def scenes_input(self, value: str) -> None:
        self.inputs.scenes_input = value

    @property
    def auto_audio_input(self) -> str:
        return self.auto_inputs.audio_input

    @auto_audio_input.setter
    def auto_audio_input(self, value: str) -> None:
        self.auto_inputs.audio_input = value

    @property
    def auto_subtitle_input(self) -> str:
        return self.auto_inputs.subtitle_input

    @auto_subtitle_input.setter
    def auto_subtitle_input(self, value: str) -> None:
        self.auto_inputs.subtitle_input = value

    @property
    def auto_output_input(self) -> str:
        return self.auto_inputs.output_input

    @auto_output_input.setter
    def auto_output_input(self, value: str) -> None:
        self.auto_inputs.output_input = value

    @property
    def auto_cover_input(self) -> str:
        return self.auto_inputs.cover_input

    @auto_cover_input.setter
    def auto_cover_input(self, value: str) -> None:
        self.auto_inputs.cover_input = value

    @property
    def auto_scenes_input(self) -> str:
        return self.auto_inputs.scenes_input

    @auto_scenes_input.setter
    def auto_scenes_input(self, value: str) -> None:
        self.auto_inputs.scenes_input = value

    @property
    def lock_to_audio_handoff(self) -> bool:
        return self.handoff.lock_to_audio_handoff

    @lock_to_audio_handoff.setter
    def lock_to_audio_handoff(self, value: bool) -> None:
        self.handoff.lock_to_audio_handoff = value

    @property
    def lock_to_image_handoff(self) -> bool:
        return self.handoff.lock_to_image_handoff

    @lock_to_image_handoff.setter
    def lock_to_image_handoff(self, value: bool) -> None:
        self.handoff.lock_to_image_handoff = value

    @property
    def last_output(self) -> str:
        return self.results.last_output

    @last_output.setter
    def last_output(self, value: str) -> None:
        self.results.last_output = value


def video_session(state: SessionState | None = None) -> VideoSession:
    session = _get_session_state(state)
    ensure_session_defaults(session)
    return VideoSession(session)
