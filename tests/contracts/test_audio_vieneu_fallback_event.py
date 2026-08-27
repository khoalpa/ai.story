from __future__ import annotations

import asyncio

from audio.adapters.vieneu_engine_lifecycle import VieneuEngineLifecycle
from audio.gui import helpers
from audio.pipeline.segment_planner import Segment
from audio.render_events import RenderProviderFallbackEvent
from audio.services import tts_render


def test_engine_lifecycle_caches_and_clears_instances() -> None:
    lifecycle = VieneuEngineLifecycle()
    created: list[object] = []

    def factory() -> object:
        engine = object()
        created.append(engine)
        return engine

    first = lifecycle.get_or_create(("standard", "cpu"), factory)
    second = lifecycle.get_or_create(("standard", "cpu"), factory)
    assert first is second
    assert len(created) == 1

    lifecycle.clear()
    third = lifecycle.get_or_create(("standard", "cpu"), factory)
    assert third is not first
    assert len(created) == 2


def test_vieneu_batch_failure_emits_fallback_event(monkeypatch, tmp_path) -> None:
    class FakeEngine:
        def get_preset_voice(self, voice_id: str) -> dict[str, str]:
            return {"voice_id": voice_id}

        def list_preset_voices(self) -> list[tuple[str, str]]:
            return [("Narrator", "narrator")]

        def infer_batch(self, **_kwargs):  # noqa: ANN003, ANN201
            raise RuntimeError("batch unavailable")

    async def fake_synthesize(_seg, out_wav, *_args, **_kwargs) -> None:  # noqa: ANN001, ANN003
        out_wav.write_bytes(b"fallback-audio")

    monkeypatch.setattr(tts_render, "get_vieneu_engine", lambda **_kwargs: FakeEngine())
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_for_runtime", lambda value, *_args, **_kwargs: str(value))
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_name", lambda value, _mode: str(value))
    monkeypatch.setattr(tts_render, "synthesize_segment_with_vieneu_async", fake_synthesize)

    events = []
    config = tts_render.TtsRenderConfig(
        wav_dir=tmp_path,
        voice_map_vi={"narrator": "narrator"},
        voice_map_en={"narrator": "narrator"},
        abbr_map={},
        tts_provider="vieneu",
        vieneu_mode="standard",
        vieneu_model_name="model",
        vieneu_device="cpu",
        vieneu_render_use_batch=True,
        event_sink=events.append,
        cache_enabled=False,
    )
    segment = Segment(text="Xin chào", voice="narrator", rate="0%", lang="vi", lang_from_tag=True)

    asyncio.run(tts_render.render_tts_segments_async([segment], config))

    fallback_events = [event for event in events if isinstance(event, RenderProviderFallbackEvent)]
    assert len(fallback_events) == 1
    assert fallback_events[0].payload == {
        "provider": "vieneu",
        "from_mode": "batch",
        "to_mode": "per_segment",
        "reason": "batch unavailable",
    }
    assert (tmp_path / "seg_000.wav").read_bytes() == b"fallback-audio"


def test_gui_progress_collector_displays_fallback_warning(monkeypatch) -> None:
    class Slot:
        def __init__(self) -> None:
            self.warnings: list[str] = []

        def progress(self, *_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            return None

        def warning(self, message: str) -> None:
            self.warnings.append(message)

        def __getattr__(self, _name):  # noqa: ANN001, ANN204
            return lambda *_args, **_kwargs: None

    monkeypatch.setattr(helpers, "render_runtime_usage_compact", lambda: None)
    status = Slot()
    collector = helpers.ProgressCollector(status, Slot(), Slot(), Slot())

    collector(RenderProviderFallbackEvent(
        provider="vieneu",
        from_mode="batch",
        to_mode="per_segment",
        reason="batch unavailable",
    ))

    assert status.warnings == ["vieneu batch failed; continuing with per_segment rendering."]
