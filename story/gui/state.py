from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

from story.testing import DEFAULT_TEST_SYSTEM_PROMPT, DEFAULT_TEST_USER_PROMPT

SessionState = MutableMapping[str, Any]

STORY_BRIEF_TEXT_KEY = "story_brief_text"
STORY_SYSTEM_PROMPT_TEXT_KEY = "story_system_prompt_text"
STORY_LAST_RESULT_KEY = "story_last_result"
STORY_LAST_ERROR_KEY = "story_last_error"
STORY_LAST_HISTORY_KEY = "story_last_history"
STORY_OUTLINE_HISTORY_KEY = "story_outline_history"
STORY_DRAFT_HISTORY_KEY = "story_draft_history"
STORY_LAST_FAILED_RESULT_KEY = "story_last_failed_result"
STORY_LAST_ERROR_CONTEXT_KEY = "story_last_error_context"
STORY_SELECTED_BRIEF_KEY = "story_selected_brief"
STORY_SELECTED_SYSTEM_PROMPT_KEY = "story_selected_system_prompt"
STORY_SELECTED_BRIEF_LABEL_KEY = "story_selected_brief_label"
STORY_SELECTED_SYSTEM_PROMPT_LABEL_KEY = "story_selected_system_prompt_label"
STORY_RECOMMENDED_BRIEF_LABEL_KEY = "story_recommended_brief_label"
STORY_RECOMMENDED_SYSTEM_PROMPT_LABEL_KEY = "story_recommended_system_prompt_label"
STORY_MODE_LAST_KEY = "story_mode_last"
STORY_LAST_PLAIN_SCRIPT_PATH_KEY = "story_last_plain_script_path"
STORY_LLM_TEST_SYSTEM_PROMPT_KEY = "story_llm_test_system_prompt"
STORY_LLM_TEST_USER_PROMPT_KEY = "story_llm_test_user_prompt"
STORY_LLM_TEST_SYSTEM_PROMPT_INPUT_KEY = "story_llm_test_system_prompt_input"
STORY_LLM_TEST_USER_PROMPT_INPUT_KEY = "story_llm_test_user_prompt_input"
STORY_LLM_TEST_RESET_PENDING_KEY = "story_llm_test_reset_pending"
STORY_LLM_TEST_RESULT_KEY = "story_llm_test_result"
STORY_LLM_TEST_ERROR_KEY = "story_llm_test_error"
STORY_LLM_TEST_CFG_FINGERPRINT_KEY = "story_llm_test_cfg_fingerprint"
STORY_LLM_PROVIDER_ID_KEY = "story_llm_provider_id"
STORY_LLM_PROVIDER_LAST_KEY = "story_llm_provider_last"
STORY_LLM_PROFILE_ID_KEY = "story_llm_profile_id"
STORY_LLM_PROFILE_LAST_KEY = "story_llm_profile_last"
STORY_LLM_BASE_URL_INPUT_KEY = "story_llm_base_url_input"
STORY_LLM_MODEL_INPUT_KEY = "story_llm_model_input"
STORY_LLM_API_KEY_INPUT_KEY = "story_llm_api_key_input"
STORY_LLM_QUICK_TEST_RESULT_KEY = "story_llm_quick_test_result"
STORY_LLM_QUICK_TEST_ERROR_KEY = "story_llm_quick_test_error"
STORY_TEST_BEFORE_GENERATE_KEY = "story_test_before_generate"

STORY_EDITOR_DEFAULTS: dict[str, object] = {
    STORY_BRIEF_TEXT_KEY: "",
    STORY_SYSTEM_PROMPT_TEXT_KEY: "",
    STORY_MODE_LAST_KEY: "",
}

STORY_SELECTION_DEFAULTS: dict[str, object] = {
    STORY_SELECTED_BRIEF_KEY: "",
    STORY_SELECTED_SYSTEM_PROMPT_KEY: "",
    STORY_SELECTED_BRIEF_LABEL_KEY: "(current editor)",
    STORY_SELECTED_SYSTEM_PROMPT_LABEL_KEY: "(current editor)",
    STORY_RECOMMENDED_BRIEF_LABEL_KEY: "",
    STORY_RECOMMENDED_SYSTEM_PROMPT_LABEL_KEY: "",
}

STORY_RESULT_DEFAULTS: dict[str, object] = {
    STORY_LAST_RESULT_KEY: None,
    STORY_LAST_ERROR_KEY: "",
    STORY_LAST_HISTORY_KEY: [],
    STORY_OUTLINE_HISTORY_KEY: [],
    STORY_DRAFT_HISTORY_KEY: [],
    STORY_LAST_FAILED_RESULT_KEY: None,
    STORY_LAST_ERROR_CONTEXT_KEY: None,
    STORY_LAST_PLAIN_SCRIPT_PATH_KEY: "",
}

STORY_LLM_TEST_DEFAULTS: dict[str, object] = {
    STORY_LLM_TEST_SYSTEM_PROMPT_KEY: DEFAULT_TEST_SYSTEM_PROMPT,
    STORY_LLM_TEST_USER_PROMPT_KEY: DEFAULT_TEST_USER_PROMPT,
    STORY_LLM_TEST_SYSTEM_PROMPT_INPUT_KEY: DEFAULT_TEST_SYSTEM_PROMPT,
    STORY_LLM_TEST_USER_PROMPT_INPUT_KEY: DEFAULT_TEST_USER_PROMPT,
    STORY_LLM_TEST_RESET_PENDING_KEY: False,
    STORY_LLM_TEST_RESULT_KEY: None,
    STORY_LLM_TEST_ERROR_KEY: "",
    STORY_LLM_TEST_CFG_FINGERPRINT_KEY: "",
    STORY_LLM_QUICK_TEST_RESULT_KEY: None,
    STORY_LLM_QUICK_TEST_ERROR_KEY: "",
    STORY_TEST_BEFORE_GENERATE_KEY: False,
}

STORY_PROVIDER_DEFAULTS: dict[str, object] = {
    STORY_LLM_PROVIDER_ID_KEY: "lmdeploy",
    STORY_LLM_PROVIDER_LAST_KEY: "lmdeploy",
    STORY_LLM_PROFILE_ID_KEY: "local_api_server",
    STORY_LLM_PROFILE_LAST_KEY: "local_api_server",
    STORY_LLM_BASE_URL_INPUT_KEY: "http://localhost:1234/v1",
    STORY_LLM_MODEL_INPUT_KEY: "auto",
    STORY_LLM_API_KEY_INPUT_KEY: "not-needed",
}

STORY_DEFAULTS: dict[str, object] = {
    **STORY_EDITOR_DEFAULTS,
    **STORY_SELECTION_DEFAULTS,
    **STORY_RESULT_DEFAULTS,
    **STORY_LLM_TEST_DEFAULTS,
    **STORY_PROVIDER_DEFAULTS,
}


def _get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return cast(SessionState, st.session_state)


def ensure_session_defaults(state: SessionState | None = None) -> None:
    session = _get_session_state(state)
    for key, value in STORY_DEFAULTS.items():
        session.setdefault(key, value)


@dataclass
class StoryEditorState:
    state: SessionState

    @property
    def brief_text(self) -> str:
        return str(self.state.get(STORY_BRIEF_TEXT_KEY) or "")

    @brief_text.setter
    def brief_text(self, value: str) -> None:
        self.state[STORY_BRIEF_TEXT_KEY] = value or ""

    @property
    def system_prompt_text(self) -> str:
        return str(self.state.get(STORY_SYSTEM_PROMPT_TEXT_KEY) or "")

    @system_prompt_text.setter
    def system_prompt_text(self, value: str) -> None:
        self.state[STORY_SYSTEM_PROMPT_TEXT_KEY] = value or ""


@dataclass
class StorySelectionState:
    state: SessionState

    @property
    def selected_brief_label(self) -> str:
        return str(self.state.get(STORY_SELECTED_BRIEF_LABEL_KEY) or "")

    @selected_brief_label.setter
    def selected_brief_label(self, value: str) -> None:
        self.state[STORY_SELECTED_BRIEF_LABEL_KEY] = value or ""

    @property
    def selected_system_prompt_label(self) -> str:
        return str(self.state.get(STORY_SELECTED_SYSTEM_PROMPT_LABEL_KEY) or "")

    @selected_system_prompt_label.setter
    def selected_system_prompt_label(self, value: str) -> None:
        self.state[STORY_SELECTED_SYSTEM_PROMPT_LABEL_KEY] = value or ""


@dataclass
class StoryResultState:
    state: SessionState

    @property
    def last_result(self) -> Any:
        return self.state.get(STORY_LAST_RESULT_KEY)

    @last_result.setter
    def last_result(self, value: Any) -> None:
        self.state[STORY_LAST_RESULT_KEY] = value

    @property
    def last_error(self) -> str:
        return str(self.state.get(STORY_LAST_ERROR_KEY) or "")

    @last_error.setter
    def last_error(self, value: str) -> None:
        self.state[STORY_LAST_ERROR_KEY] = value or ""

    @property
    def last_plain_script_path(self) -> str:
        return str(self.state.get(STORY_LAST_PLAIN_SCRIPT_PATH_KEY) or "")

    @last_plain_script_path.setter
    def last_plain_script_path(self, value: str) -> None:
        self.state[STORY_LAST_PLAIN_SCRIPT_PATH_KEY] = value or ""


@dataclass
class StoryLLMTestState:
    state: SessionState

    @property
    def system_prompt(self) -> str:
        return str(self.state.get(STORY_LLM_TEST_SYSTEM_PROMPT_KEY) or "")

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        self.state[STORY_LLM_TEST_SYSTEM_PROMPT_KEY] = value or ""

    @property
    def user_prompt(self) -> str:
        return str(self.state.get(STORY_LLM_TEST_USER_PROMPT_KEY) or "")

    @user_prompt.setter
    def user_prompt(self, value: str) -> None:
        self.state[STORY_LLM_TEST_USER_PROMPT_KEY] = value or ""


@dataclass
class StorySession:
    state: SessionState

    @property
    def editor(self) -> StoryEditorState:
        return StoryEditorState(self.state)

    @property
    def selection(self) -> StorySelectionState:
        return StorySelectionState(self.state)

    @property
    def results(self) -> StoryResultState:
        return StoryResultState(self.state)

    @property
    def llm_test(self) -> StoryLLMTestState:
        return StoryLLMTestState(self.state)

    @property
    def brief_text(self) -> str:
        return self.editor.brief_text

    @brief_text.setter
    def brief_text(self, value: str) -> None:
        self.editor.brief_text = value

    @property
    def system_prompt_text(self) -> str:
        return self.editor.system_prompt_text

    @system_prompt_text.setter
    def system_prompt_text(self, value: str) -> None:
        self.editor.system_prompt_text = value

    @property
    def last_result(self) -> Any:
        return self.results.last_result

    @last_result.setter
    def last_result(self, value: Any) -> None:
        self.results.last_result = value

    @property
    def last_error(self) -> str:
        return self.results.last_error

    @last_error.setter
    def last_error(self, value: str) -> None:
        self.results.last_error = value

    @property
    def selected_brief_label(self) -> str:
        return self.selection.selected_brief_label

    @selected_brief_label.setter
    def selected_brief_label(self, value: str) -> None:
        self.selection.selected_brief_label = value

    @property
    def selected_system_prompt_label(self) -> str:
        return self.selection.selected_system_prompt_label

    @selected_system_prompt_label.setter
    def selected_system_prompt_label(self, value: str) -> None:
        self.selection.selected_system_prompt_label = value

    @property
    def last_plain_script_path(self) -> str:
        return self.results.last_plain_script_path

    @last_plain_script_path.setter
    def last_plain_script_path(self, value: str) -> None:
        self.results.last_plain_script_path = value


def story_session(state: SessionState | None = None) -> StorySession:
    session = _get_session_state(state)
    ensure_session_defaults(session)
    return StorySession(session)
