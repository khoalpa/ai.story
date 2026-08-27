from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewSpec:
    id: str
    label: str
    description: str


AUDIO_VIEW_SPECS = (
    ViewSpec("inputs", "Inputs", "Prepare and review the script used by Audio."),
    ViewSpec("run", "Run", "Validate and render the current Audio job."),
    ViewSpec("batch", "Batch", "Run manifests and retry eligible Audio jobs."),
    ViewSpec("doctor", "Doctor", "Check runtime, provider, asset, and configuration readiness."),
    ViewSpec("test", "Test", "Preview the selected TTS provider and voice before a full run."),
    ViewSpec("results_logs", "Results & Logs", "Inspect the latest Audio output, preview, and event log."),
    ViewSpec("history", "History", "Review completed and failed Audio jobs."),
)

AUDIO_VIEW_IDS = tuple(spec.id for spec in AUDIO_VIEW_SPECS)
AUDIO_VIEW_BY_ID = {spec.id: spec for spec in AUDIO_VIEW_SPECS}

_LEGACY_VIEW_IDS = {
    "Input": "inputs",
    "Inputs": "inputs",
    "Run": "run",
    "Batch": "batch",
    "Doctor": "doctor",
    "Test TTS": "test",
    "Test": "test",
    "Preview & Logs": "results_logs",
    "Results & Logs": "results_logs",
    "History": "history",
}


def normalize_audio_view_id(value: str, default: str = "inputs") -> str:
    candidate = _LEGACY_VIEW_IDS.get(str(value or "").strip(), str(value or "").strip())
    return candidate if candidate in AUDIO_VIEW_BY_ID else default
