from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewSpec:
    id: str
    label: str
    description: str


VIDEO_VIEW_SPECS = (
    ViewSpec("inputs", "Inputs", "Prepare and review the assets used by Video."),
    ViewSpec("run", "Run", "Validate and render the current Video job."),
    ViewSpec("doctor", "Doctor", "Check runtime, input, and image readiness."),
    ViewSpec("test", "Test", "Resolve inputs and preview the effective Video plan."),
    ViewSpec("results_logs", "Results & Logs", "Inspect the latest Video output and runtime logs."),
    ViewSpec("history", "History", "Review Video renders from the current session."),
)

VIDEO_VIEW_IDS = tuple(spec.id for spec in VIDEO_VIEW_SPECS)
VIDEO_VIEW_BY_ID = {spec.id: spec for spec in VIDEO_VIEW_SPECS}

_LEGACY_VIEW_IDS = {
    "Input": "inputs",
    "Inputs": "inputs",
    "Run": "run",
    "Doctor": "doctor",
    "Test": "test",
    "Preview & Logs": "results_logs",
    "Results & Logs": "results_logs",
    "History": "history",
}


def normalize_video_view_id(value: str, default: str = "inputs") -> str:
    candidate = _LEGACY_VIEW_IDS.get(str(value or "").strip(), str(value or "").strip())
    return candidate if candidate in VIDEO_VIEW_BY_ID else default
