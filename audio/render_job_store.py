from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Optional, Protocol
from uuid import uuid4

from audio.render_events import (
    AppDebugSavedEvent,
    AppPathsResolvedEvent,
    AppRenderCompletedEvent,
    AppValidationCompletedEvent,
    RenderEvent,
    RenderPhaseCompletedEvent,
    RenderPhaseStartedEvent,
)


@dataclass(frozen=True)
class JobRunRecord:
    job_id: str
    status: str = "running"
    input_path: Optional[Path] = None
    output_dir: Optional[Path] = None
    last_event_name: Optional[str] = None
    total_events: int = 0
    app_phase_starts: tuple[str, ...] = ()
    app_phase_completions: tuple[str, ...] = ()
    render_phase_starts: tuple[str, ...] = ()
    render_phase_completions: tuple[str, ...] = ()
    validation_exit_code: Optional[int] = None
    validation_errors_count: int = 0
    validation_warnings_count: int = 0
    debug_json: Optional[Path] = None
    rendered_audio: Optional[Path] = None
    rendered_subtitle: Optional[Path] = None


class JobStore(Protocol):
    def save(self, record: JobRunRecord) -> JobRunRecord: ...

    def get(self, job_id: str) -> Optional[JobRunRecord]: ...

    def list_runs(self) -> tuple[JobRunRecord, ...]: ...


@dataclass
class InMemoryJobStore(JobStore):
    _runs: dict[str, JobRunRecord] = field(default_factory=dict)
    _history: list[str] = field(default_factory=list)

    def save(self, record: JobRunRecord) -> JobRunRecord:
        is_new = record.job_id not in self._runs
        self._runs[record.job_id] = record
        if is_new:
            self._history.append(record.job_id)
        return record

    def get(self, job_id: str) -> Optional[JobRunRecord]:
        return self._runs.get(job_id)

    def list_runs(self) -> tuple[JobRunRecord, ...]:
        return tuple(self._runs[job_id] for job_id in self._history)


@dataclass
class JsonFileJobStore(JobStore):
    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.path.exists():
            self._write_payload({"history": [], "runs": {}})

    def save(self, record: JobRunRecord) -> JobRunRecord:
        payload = self._read_payload()
        history = list(payload.get("history", []))
        runs = dict(payload.get("runs", {}))
        if record.job_id not in runs:
            history.append(record.job_id)
        runs[record.job_id] = _serialize_record(record)
        self._write_payload({"history": history, "runs": runs})
        return record

    def get(self, job_id: str) -> Optional[JobRunRecord]:
        payload = self._read_payload()
        raw = dict(payload.get("runs", {})).get(job_id)
        if raw is None:
            return None
        return _deserialize_record(raw)

    def list_runs(self) -> tuple[JobRunRecord, ...]:
        payload = self._read_payload()
        runs = dict(payload.get("runs", {}))
        history = list(payload.get("history", []))
        return tuple(_deserialize_record(runs[job_id]) for job_id in history if job_id in runs)

    def _read_payload(self) -> dict:
        if not self.path.exists():
            return {"history": [], "runs": {}}
        with self.path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write_payload(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        tmp_path.replace(self.path)


@dataclass
class JobStoreSubscriber:
    store: JobStore
    job_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        self.store.save(JobRunRecord(job_id=self.job_id))

    @property
    def record(self) -> JobRunRecord:
        record = self.store.get(self.job_id)
        if record is None:
            record = JobRunRecord(job_id=self.job_id)
            self.store.save(record)
        return record

    def handle_event(self, event: RenderEvent) -> None:
        record = self.record
        payload = dict(event.payload)
        updates: dict[str, object] = {
            "last_event_name": event.name,
            "total_events": record.total_events + 1,
        }

        if isinstance(event, AppPathsResolvedEvent) or event.name == "app.paths.resolved":
            raw_input = payload.get("input_path")
            raw_output = payload.get("output_dir")
            updates["input_path"] = Path(raw_input) if raw_input is not None else record.input_path
            updates["output_dir"] = Path(raw_output) if raw_output is not None else record.output_dir
        elif event.name == "app.phase.started":
            phase = str(payload.get("phase", ""))
            updates["app_phase_starts"] = record.app_phase_starts + (phase,)
        elif event.name == "app.phase.completed":
            phase = str(payload.get("phase", ""))
            updates["app_phase_completions"] = record.app_phase_completions + (phase,)
        elif isinstance(event, RenderPhaseStartedEvent) or event.name == "render.phase.started":
            phase = str(payload.get("phase", ""))
            updates["render_phase_starts"] = record.render_phase_starts + (phase,)
        elif isinstance(event, RenderPhaseCompletedEvent) or event.name == "render.phase.completed":
            phase = str(payload.get("phase", ""))
            updates["render_phase_completions"] = record.render_phase_completions + (phase,)
        elif isinstance(event, AppValidationCompletedEvent) or event.name == "app.validation.completed":
            exit_code = int(payload.get("exit_code", 0))
            updates["status"] = "validation_failed" if exit_code else "validated"
            updates["validation_exit_code"] = exit_code
            updates["validation_errors_count"] = len(tuple(payload.get("errors", ())))
            updates["validation_warnings_count"] = int(payload.get("warnings_count", 0))
        elif isinstance(event, AppDebugSavedEvent) or event.name == "app.debug.saved":
            debug_json = payload.get("debug_json")
            updates["status"] = "debugged"
            updates["debug_json"] = Path(debug_json) if debug_json is not None else None
        elif isinstance(event, AppRenderCompletedEvent) or event.name == "app.render.completed":
            artifacts = payload.get("render_artifacts")
            updates["status"] = "completed"
            if artifacts is not None:
                updates["rendered_audio"] = getattr(artifacts, "out_file", None)
                updates["rendered_subtitle"] = getattr(artifacts, "srt_path", None)

        self.store.save(replace(record, **updates))


def _serialize_record(record: JobRunRecord) -> dict:
    payload = asdict(record)
    for key, value in tuple(payload.items()):
        if isinstance(value, Path):
            payload[key] = str(value)
    return payload


def _deserialize_record(raw: dict) -> JobRunRecord:
    payload = dict(raw)
    for key in ("input_path", "output_dir", "debug_json", "rendered_audio", "rendered_subtitle"):
        value = payload.get(key)
        if value is not None:
            payload[key] = Path(value)
    for key in (
        "app_phase_starts",
        "app_phase_completions",
        "render_phase_starts",
        "render_phase_completions",
    ):
        payload[key] = tuple(payload.get(key, ()))
    return JobRunRecord(**payload)
