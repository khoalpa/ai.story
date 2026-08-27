from __future__ import annotations

import wave

from audio.gui import helpers
from audio.render_events import RenderEvent
from audio.services.render_orchestration import _GeneratedWavDurationTracker


def _write_silent_wav(path, seconds: float) -> None:  # noqa: ANN001
    sample_rate = 8_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\x00\x00" * int(sample_rate * seconds))


def test_generated_wav_duration_tracker_accumulates_only_completed_segments(tmp_path) -> None:
    tracker = _GeneratedWavDurationTracker(tmp_path, 3)
    _write_silent_wav(tmp_path / "seg_000.wav", 1.25)
    _write_silent_wav(tmp_path / "seg_002.wav", 2.5)

    assert tracker.refresh() == 3.75
    assert tracker.refresh() == 3.75

    _write_silent_wav(tmp_path / "seg_001.wav", 0.5)
    assert tracker.refresh() == 4.25


def test_gui_tts_progress_displays_actual_generated_voice_duration(monkeypatch) -> None:
    class Slot:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def progress(self, *_args, **kwargs) -> None:  # noqa: ANN002, ANN003
            if kwargs.get("text"):
                self.messages.append(kwargs["text"])

        def info(self, message: str) -> None:
            self.messages.append(message)

        def __getattr__(self, _name):  # noqa: ANN001, ANN204
            return lambda *_args, **_kwargs: None

    monkeypatch.setattr(helpers, "render_runtime_usage_compact", lambda: None)
    status = Slot()
    collector = helpers.ProgressCollector(status, Slot(), Slot(), Slot())
    collector(
        RenderEvent(
            name="render.phase.progress",
            payload={
                "phase": "tts",
                "completed": 201,
                "total": 721,
                "unit": "segments",
                "actual_audio_seconds": 4_922,
            },
        )
    )

    assert any("201/721 segments - voice generated 1:22:02" in message for message in status.messages)
