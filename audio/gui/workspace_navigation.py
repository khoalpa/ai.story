from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]

WORKSPACE_ACTIVE_APP_KEY = "workspace_active_app"
WORKSPACE_ACTIVE_APP_SELECTOR_KEY = "workspace_active_app_selector"
WORKSPACE_PENDING_APP_KEY = "workspace_pending_app"
WORKSPACE_PENDING_VIEW_KEY = "workspace_pending_view"
WORKSPACE_PENDING_FIELD_KEY = "workspace_pending_field"
WORKSPACE_STORY_TARGET_VIEW_KEY = "workspace_story_target_view"
WORKSPACE_AUDIO_TARGET_VIEW_KEY = "workspace_audio_target_view"
WORKSPACE_IMAGE_TARGET_VIEW_KEY = "workspace_image_target_view"
WORKSPACE_VIDEO_TARGET_VIEW_KEY = "workspace_video_target_view"
WORKSPACE_STORY_TARGET_FIELD_KEY = "workspace_story_target_field"
WORKSPACE_AUDIO_TARGET_FIELD_KEY = "workspace_audio_target_field"
WORKSPACE_IMAGE_TARGET_FIELD_KEY = "workspace_image_target_field"
WORKSPACE_VIDEO_TARGET_FIELD_KEY = "workspace_video_target_field"

TARGET_VIEW_KEY_MAP = {
    "Story": WORKSPACE_STORY_TARGET_VIEW_KEY,
    "Audio": WORKSPACE_AUDIO_TARGET_VIEW_KEY,
    "Image": WORKSPACE_IMAGE_TARGET_VIEW_KEY,
    "Video": WORKSPACE_VIDEO_TARGET_VIEW_KEY,
}

TARGET_FIELD_KEY_MAP = {
    "Story": WORKSPACE_STORY_TARGET_FIELD_KEY,
    "Audio": WORKSPACE_AUDIO_TARGET_FIELD_KEY,
    "Image": WORKSPACE_IMAGE_TARGET_FIELD_KEY,
    "Video": WORKSPACE_VIDEO_TARGET_FIELD_KEY,
}


def _get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return cast(SessionState, st.session_state)


def get_workspace_text(key: str, default: str = "", *, state: SessionState | None = None) -> str:
    session = _get_session_state(state)
    return str(session.get(key) or default)


@dataclass
class WorkspaceNavigationState:
    state: SessionState

    @property
    def active_app(self) -> str:
        return get_workspace_text(WORKSPACE_ACTIVE_APP_KEY, "Overview", state=self.state)

    @active_app.setter
    def active_app(self, value: str) -> None:
        self.state[WORKSPACE_ACTIVE_APP_KEY] = value or "Overview"

    @property
    def active_app_selector(self) -> str:
        return get_workspace_text(WORKSPACE_ACTIVE_APP_SELECTOR_KEY, "Overview", state=self.state)

    @active_app_selector.setter
    def active_app_selector(self, value: str) -> None:
        self.state[WORKSPACE_ACTIVE_APP_SELECTOR_KEY] = value or "Overview"

    @property
    def pending_app(self) -> str:
        return get_workspace_text(WORKSPACE_PENDING_APP_KEY, state=self.state).strip()

    @pending_app.setter
    def pending_app(self, value: str) -> None:
        self.state[WORKSPACE_PENDING_APP_KEY] = (value or "").strip()

    @property
    def pending_view(self) -> str:
        return get_workspace_text(WORKSPACE_PENDING_VIEW_KEY, state=self.state).strip()

    @pending_view.setter
    def pending_view(self, value: str) -> None:
        self.state[WORKSPACE_PENDING_VIEW_KEY] = (value or "").strip()

    @property
    def pending_field(self) -> str:
        return get_workspace_text(WORKSPACE_PENDING_FIELD_KEY, state=self.state).strip()

    @pending_field.setter
    def pending_field(self, value: str) -> None:
        self.state[WORKSPACE_PENDING_FIELD_KEY] = (value or "").strip()

    def get_target_view(self, app_name: str, default: str = "Run") -> str:
        key = TARGET_VIEW_KEY_MAP.get(app_name)
        if not key:
            return default
        value = get_workspace_text(key, state=self.state).strip()
        return value or default

    def set_target_view(self, app_name: str, value: str) -> None:
        key = TARGET_VIEW_KEY_MAP.get(app_name)
        if key:
            self.state[key] = value or ""


    def get_target_field(self, app_name: str, default: str = "") -> str:
        key = TARGET_FIELD_KEY_MAP.get(app_name)
        if not key:
            return default
        value = get_workspace_text(key, state=self.state).strip()
        return value or default

    def set_target_field(self, app_name: str, value: str) -> None:
        key = TARGET_FIELD_KEY_MAP.get(app_name)
        if key:
            self.state[key] = value or ""


def workspace_navigation_state(state: SessionState | None = None) -> WorkspaceNavigationState:
    return WorkspaceNavigationState(_get_session_state(state))
