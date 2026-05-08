from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, MutableMapping, cast

import streamlit as st

SessionState = MutableMapping[str, Any]

WORKSPACE_LAST_JOB_APP_KEY = "workspace_last_job_app"
WORKSPACE_LAST_JOB_STAGE_KEY = "workspace_last_job_stage"
WORKSPACE_LAST_JOB_STATUS_KEY = "workspace_last_job_status"
WORKSPACE_LAST_JOB_PROGRESS_KEY = "workspace_last_job_progress"
WORKSPACE_LAST_JOB_OUTPUT_KEY = "workspace_last_job_output"
WORKSPACE_LAST_JOB_ERROR_KEY = "workspace_last_job_error"
WORKSPACE_LAST_JOB_SUMMARY_KEY = "workspace_last_job_summary"
WORKSPACE_JOB_TIMELINE_KEY = "workspace_job_timeline"
WORKSPACE_NOW_OVERRIDE_KEY = "_workspace_now_override"


def _get_session_state(state: SessionState | None = None) -> SessionState:
    if state is not None:
        return state
    return cast(SessionState, st.session_state)


def _get_text(key: str, default: str = "", *, state: SessionState) -> str:
    return str(state.get(key) or default)


@dataclass
class GlobalRunMonitorState:
    state: SessionState

    @property
    def app(self) -> str:
        return _get_text(WORKSPACE_LAST_JOB_APP_KEY, state=self.state)

    @app.setter
    def app(self, value: str) -> None:
        self.state[WORKSPACE_LAST_JOB_APP_KEY] = value or ""

    @property
    def stage(self) -> str:
        return _get_text(WORKSPACE_LAST_JOB_STAGE_KEY, state=self.state)

    @stage.setter
    def stage(self, value: str) -> None:
        self.state[WORKSPACE_LAST_JOB_STAGE_KEY] = value or ""

    @property
    def status(self) -> str:
        return _get_text(WORKSPACE_LAST_JOB_STATUS_KEY, "idle", state=self.state)

    @status.setter
    def status(self, value: str) -> None:
        self.state[WORKSPACE_LAST_JOB_STATUS_KEY] = value or "idle"

    @property
    def progress(self) -> int:
        try:
            return int(self.state.get(WORKSPACE_LAST_JOB_PROGRESS_KEY) or 0)
        except Exception:
            return 0

    @progress.setter
    def progress(self, value: int | float) -> None:
        self.state[WORKSPACE_LAST_JOB_PROGRESS_KEY] = int(round(float(value)))

    @property
    def output(self) -> str:
        return _get_text(WORKSPACE_LAST_JOB_OUTPUT_KEY, state=self.state)

    @output.setter
    def output(self, value: str) -> None:
        self.state[WORKSPACE_LAST_JOB_OUTPUT_KEY] = value or ""

    @property
    def error(self) -> str:
        return _get_text(WORKSPACE_LAST_JOB_ERROR_KEY, state=self.state)

    @error.setter
    def error(self, value: str) -> None:
        self.state[WORKSPACE_LAST_JOB_ERROR_KEY] = value or ""

    @property
    def summary(self) -> dict[str, Any] | None:
        value = self.state.get(WORKSPACE_LAST_JOB_SUMMARY_KEY)
        return value if isinstance(value, dict) or value is None else cast(dict[str, Any] | None, value)

    @summary.setter
    def summary(self, value: dict[str, Any] | None) -> None:
        self.state[WORKSPACE_LAST_JOB_SUMMARY_KEY] = value

    @property
    def timeline(self) -> list[dict[str, str]]:
        value = self.state.get(WORKSPACE_JOB_TIMELINE_KEY) or []
        return list(value)

    @timeline.setter
    def timeline(self, value: list[dict[str, str]]) -> None:
        self.state[WORKSPACE_JOB_TIMELINE_KEY] = list(value)

    def snapshot(self) -> dict[str, object]:
        return {
            "app": self.app,
            "stage": self.stage,
            "status": self.status,
            "progress": self.progress,
            "output": self.output,
            "error": self.error,
            "summary": self.summary,
        }

    def append_timeline_event(
        self,
        *,
        app: str,
        stage: str,
        status: str,
        message: str = "",
        output_path: str = "",
        error_text: str = "",
        limit: int = 20,
    ) -> None:
        timestamp = _get_text(WORKSPACE_NOW_OVERRIDE_KEY, state=self.state)
        if not timestamp:
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
            except Exception:
                timestamp = ""
        item = {
            "time": timestamp,
            "app": app,
            "stage": stage,
            "status": status,
            "message": message,
            "output": output_path,
            "error": error_text,
        }
        timeline = self.timeline
        timeline.insert(0, item)
        self.timeline = timeline[: max(1, int(limit))]


def global_run_monitor_state(state: SessionState | None = None) -> GlobalRunMonitorState:
    return GlobalRunMonitorState(_get_session_state(state))
