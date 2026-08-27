from __future__ import annotations

from audio.render_events import RenderEvent, RenderPhaseCompletedEvent
from audio.render_job_store import InMemoryJobStore, JobStoreSubscriber
from audio.render_observers import JobTelemetrySubscriber


def test_phase_durations_and_realtime_factor_are_persisted() -> None:
    telemetry = JobTelemetrySubscriber()
    store_subscriber = JobStoreSubscriber(store=InMemoryJobStore())
    phase_event = RenderPhaseCompletedEvent(
        phase="tts",
        details={"elapsed_ms": 1250.5, "realtime_factor": 0.8},
    )
    total_event = RenderEvent(
        name="render.telemetry.completed",
        payload={"elapsed_ms": 1500.0, "realtime_factor": 0.95},
    )
    cache_event = RenderEvent(
        name="render.tts.cache.resolved",
        payload={"hit_count": 7, "miss_count": 2},
    )

    for event in (phase_event, total_event, cache_event):
        telemetry.handle_event(event)
        store_subscriber.handle_event(event)

    assert telemetry.snapshot.render_phase_durations_ms == {"tts": 1250.5}
    assert telemetry.snapshot.render_realtime_factor == 0.95
    assert telemetry.snapshot.tts_cache_hits == 7
    assert telemetry.snapshot.tts_cache_misses == 2
    assert store_subscriber.record.render_phase_durations_ms == {"tts": 1250.5}
    assert store_subscriber.record.render_realtime_factor == 0.95
    assert store_subscriber.record.tts_cache_hits == 7
    assert store_subscriber.record.tts_cache_misses == 2
