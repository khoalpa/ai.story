from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]

IMAGE_HANDOFF_DIR_KEY = "image_handoff_dir"
IMAGE_INPUT_DIR_KEY = "image_input_dir"
IMAGE_OUTPUT_DIR_KEY = "image_output_dir"
IMAGE_SOURCE_KIND_KEY = "image_source_kind"
IMAGE_LAST_COVER_OUTPUT_KEY = "image_last_cover_output"
IMAGE_LAST_SCENES_DIR_KEY = "image_last_scenes_dir"
IMAGE_LAST_RESULT_KEY = "image_last_result"
IMAGE_LAST_ERROR_KEY = "image_last_error"
IMAGE_LAST_LOGS_KEY = "image_last_logs"
IMAGE_RUN_HISTORY_KEY = "image_run_history"
IMAGE_LOCK_TO_STORY_HANDOFF_KEY = "image_lock_to_story_handoff"
IMAGE_PROMPT_OVERRIDES_KEY = "image_prompt_overrides"
IMAGE_PROMPT_EDIT_MAP_KEY = "image_prompt_edit_map"
IMAGE_INPAINT_MASK_PATH_KEY = "image_inpaint_editor_mask_path"
IMAGE_INPAINT_SOURCE_PATH_KEY = "image_inpaint_editor_source_path"
IMAGE_INPAINT_BRUSH_WIDTH_KEY = "image_inpaint_brush_width"
IMAGE_INPAINT_OVERLAY_OPACITY_KEY = "image_inpaint_overlay_opacity"
IMAGE_INPAINT_OVERLAY_COLOR_KEY = "image_inpaint_overlay_color"
IMAGE_LAST_UPSCALE_OUTPUT_KEY = "image_last_upscale_output"
IMAGE_UPSCALE_SOURCE_PATH_KEY = "image_upscale_source_path"
IMAGE_UPSCALE_SCALE_KEY = "image_upscale_scale"
IMAGE_UPSCALE_RESAMPLE_KEY = "image_upscale_resample"
IMAGE_LAST_PREVIEW_SHEET_KEY = "image_last_preview_sheet"

IMAGE_PATH_DEFAULTS: dict[str, object] = {
    IMAGE_HANDOFF_DIR_KEY: "",
    IMAGE_INPUT_DIR_KEY: "input",
    IMAGE_OUTPUT_DIR_KEY: "output",
    IMAGE_SOURCE_KIND_KEY: "handoff",
}

IMAGE_RESULT_DEFAULTS: dict[str, object] = {
    IMAGE_LAST_COVER_OUTPUT_KEY: "",
    IMAGE_LAST_SCENES_DIR_KEY: "",
    IMAGE_LAST_RESULT_KEY: None,
    IMAGE_LAST_ERROR_KEY: "",
    IMAGE_LAST_LOGS_KEY: [],
    IMAGE_RUN_HISTORY_KEY: [],
}

IMAGE_HANDOFF_DEFAULTS: dict[str, object] = {
    IMAGE_LOCK_TO_STORY_HANDOFF_KEY: True,
}

IMAGE_PROMPT_DEFAULTS: dict[str, object] = {
    IMAGE_PROMPT_OVERRIDES_KEY: {},
    IMAGE_PROMPT_EDIT_MAP_KEY: {},
    IMAGE_LAST_PREVIEW_SHEET_KEY: "",
    "image_local_auto_shorten_prompt": True,
    "image_local_auto_shorten_negative_prompt": True,
    "image_local_adetailer_enabled": True,
    "image_local_lora_enabled": False,
    "image_local_lora_model_id_or_path": "",
    "image_local_lora_scale": 1.0,
}

IMAGE_INPAINT_DEFAULTS: dict[str, object] = {
    IMAGE_INPAINT_MASK_PATH_KEY: "",
    IMAGE_INPAINT_SOURCE_PATH_KEY: "",
    IMAGE_INPAINT_BRUSH_WIDTH_KEY: 24,
    IMAGE_INPAINT_OVERLAY_OPACITY_KEY: 0.43,
    IMAGE_INPAINT_OVERLAY_COLOR_KEY: "#ff4040",
}

IMAGE_UPSCALE_DEFAULTS: dict[str, object] = {
    IMAGE_LAST_UPSCALE_OUTPUT_KEY: "",
    IMAGE_UPSCALE_SOURCE_PATH_KEY: "",
    IMAGE_UPSCALE_SCALE_KEY: 2.0,
    IMAGE_UPSCALE_RESAMPLE_KEY: "lanczos",
}

IMAGE_DEFAULTS: dict[str, object] = {
    **IMAGE_PATH_DEFAULTS,
    **IMAGE_RESULT_DEFAULTS,
    **IMAGE_HANDOFF_DEFAULTS,
    **IMAGE_PROMPT_DEFAULTS,
    **IMAGE_INPAINT_DEFAULTS,
    **IMAGE_UPSCALE_DEFAULTS,
}


def _get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return cast(SessionState, st.session_state)


def ensure_session_defaults(state: SessionState | None = None) -> None:
    session = _get_session_state(state)
    for key, value in IMAGE_DEFAULTS.items():
        session.setdefault(key, value)
    legacy_auto_shorten = session.get("image_local_auto_shorten_prompts")
    if legacy_auto_shorten is not None:
        session.setdefault("image_local_auto_shorten_prompt", bool(legacy_auto_shorten))
        session.setdefault("image_local_auto_shorten_negative_prompt", bool(legacy_auto_shorten))


@dataclass
class ImagePathsState:
    state: SessionState

    @property
    def handoff_dir(self) -> str:
        return str(self.state.get(IMAGE_HANDOFF_DIR_KEY) or "")

    @handoff_dir.setter
    def handoff_dir(self, value: str) -> None:
        self.state[IMAGE_HANDOFF_DIR_KEY] = value or ""

    @property
    def input_dir(self) -> str:
        return str(self.state.get(IMAGE_INPUT_DIR_KEY) or "")

    @input_dir.setter
    def input_dir(self, value: str) -> None:
        self.state[IMAGE_INPUT_DIR_KEY] = value or ""

    @property
    def output_dir(self) -> str:
        return str(self.state.get(IMAGE_OUTPUT_DIR_KEY) or "")

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        self.state[IMAGE_OUTPUT_DIR_KEY] = value or ""


@dataclass
class ImageResultsState:
    state: SessionState

    @property
    def last_cover_output(self) -> str:
        return str(self.state.get(IMAGE_LAST_COVER_OUTPUT_KEY) or "")

    @last_cover_output.setter
    def last_cover_output(self, value: str) -> None:
        self.state[IMAGE_LAST_COVER_OUTPUT_KEY] = value or ""

    @property
    def last_scenes_dir(self) -> str:
        return str(self.state.get(IMAGE_LAST_SCENES_DIR_KEY) or "")

    @last_scenes_dir.setter
    def last_scenes_dir(self, value: str) -> None:
        self.state[IMAGE_LAST_SCENES_DIR_KEY] = value or ""


@dataclass
class ImageSession:
    state: SessionState

    @property
    def paths(self) -> ImagePathsState:
        return ImagePathsState(self.state)

    @property
    def results(self) -> ImageResultsState:
        return ImageResultsState(self.state)

    @property
    def handoff_dir(self) -> str:
        return self.paths.handoff_dir

    @handoff_dir.setter
    def handoff_dir(self, value: str) -> None:
        self.paths.handoff_dir = value

    @property
    def input_dir(self) -> str:
        return self.paths.input_dir

    @input_dir.setter
    def input_dir(self, value: str) -> None:
        self.paths.input_dir = value

    @property
    def output_dir(self) -> str:
        return self.paths.output_dir

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        self.paths.output_dir = value


def image_session(state: SessionState | None = None) -> ImageSession:
    session = _get_session_state(state)
    ensure_session_defaults(session)
    return ImageSession(session)

