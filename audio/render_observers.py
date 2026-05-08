from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from audio.render_events import (
    AppDebugSavedEvent,
    AppRenderCompletedEvent,
    AppValidationCompletedEvent,
    RenderEvent,
    RenderEventBus,
    RenderPhaseCompletedEvent,
    RenderPhaseStartedEvent,
)
from audio.render_reporting import RenderReporter
from audio.render_job_store import InMemoryJobStore, JobStore, JobStoreSubscriber
from audio.render_job_repository import JobRepository


@dataclass(frozen=True)
class JobTelemetrySnapshot:
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


@dataclass
class JobTelemetrySubscriber:
    _snapshot: JobTelemetrySnapshot = field(default_factory=JobTelemetrySnapshot)

    @property
    def snapshot(self) -> JobTelemetrySnapshot:
        return self._snapshot

    def handle_event(self, event: RenderEvent) -> None:
        snap = self._snapshot
        payload = dict(event.payload)
        updates: dict[str, object] = {"total_events": snap.total_events + 1}

        if event.name == "app.phase.started":
            phase = str(payload.get("phase", ""))
            updates["app_phase_starts"] = snap.app_phase_starts + (phase,)
        elif event.name == "app.phase.completed":
            phase = str(payload.get("phase", ""))
            updates["app_phase_completions"] = snap.app_phase_completions + (phase,)
        elif isinstance(event, RenderPhaseStartedEvent) or event.name == "render.phase.started":
            phase = str(payload.get("phase", ""))
            updates["render_phase_starts"] = snap.render_phase_starts + (phase,)
        elif isinstance(event, RenderPhaseCompletedEvent) or event.name == "render.phase.completed":
            phase = str(payload.get("phase", ""))
            updates["render_phase_completions"] = snap.render_phase_completions + (phase,)
        elif isinstance(event, AppValidationCompletedEvent) or event.name == "app.validation.completed":
            updates["validation_exit_code"] = int(payload.get("exit_code", 0))
            updates["validation_errors_count"] = len(tuple(payload.get("errors", ())))
            updates["validation_warnings_count"] = int(payload.get("warnings_count", 0))
        elif isinstance(event, AppDebugSavedEvent) or event.name == "app.debug.saved":
            debug_json = payload.get("debug_json")
            updates["debug_json"] = Path(debug_json) if debug_json is not None else None
        elif isinstance(event, AppRenderCompletedEvent) or event.name == "app.render.completed":
            artifacts = payload.get("render_artifacts")
            if artifacts is not None:
                updates["rendered_audio"] = getattr(artifacts, "out_file", None)
                updates["rendered_subtitle"] = getattr(artifacts, "srt_path", None)

        self._snapshot = JobTelemetrySnapshot(**{**snap.__dict__, **updates})


@dataclass
class StructuredLogSubscriber:
    sink: Callable[[dict], None]

    def handle_event(self, event: RenderEvent) -> None:
        record = {
            "event": event.name,
            "message": event.message,
            "payload": dict(event.payload),
        }
        self.sink(record)


@dataclass
class CliObserverBundle:
    reporter: RenderReporter
    telemetry: JobTelemetrySubscriber
    store: JobStore
    repository: JobRepository
    store_subscriber: JobStoreSubscriber
    bus: RenderEventBus


def build_cli_observer_bundle(
    reporter: RenderReporter | None = None,
    telemetry: JobTelemetrySubscriber | None = None,
    store: JobStore | None = None,
) -> CliObserverBundle:
    reporter = reporter or RenderReporter()
    telemetry = telemetry or JobTelemetrySubscriber()
    store = store or InMemoryJobStore()
    repository = JobRepository(store)
    store_subscriber = JobStoreSubscriber(store=store)
    bus = RenderEventBus()
    bus.subscribe(reporter.handle_event)
    bus.subscribe(telemetry.handle_event)
    bus.subscribe(store_subscriber.handle_event)
    return CliObserverBundle(
        reporter=reporter,
        telemetry=telemetry,
        store=store,
        repository=repository,
        store_subscriber=store_subscriber,
        bus=bus,
    )
