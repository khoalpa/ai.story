from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from audio.adapters.ffmpeg_audio_mixer import (
    boundary_pause_target_ms,
    measure_wav_edge_silence,
    normalize_pacing_preset,
)
from audio.pipeline.script_pipeline import plan_segments_from_plain_script
from audio.pipeline.segment_planner import Segment


def _segment(**changes) -> Segment:  # noqa: ANN003
    values = {"text": "Một câu.", "voice": "narrator", "rate": "+0%"}
    values.update(changes)
    return Segment(**values)


def test_plain_script_preserves_paragraph_boundary() -> None:
    segments = plan_segments_from_plain_script("Câu một.\n\nCâu hai.\nCâu ba.")

    assert [segment.paragraph_break_before for segment in segments] == [False, True, False]


def test_natural_pacing_prioritizes_zone_paragraph_and_voice_boundaries() -> None:
    base = _segment()

    assert boundary_pause_target_ms(base, _segment(), "natural") == 550
    assert boundary_pause_target_ms(base, _segment(voice="female"), "natural") == 650
    assert boundary_pause_target_ms(base, _segment(paragraph_break_before=True), "natural") == 800
    assert boundary_pause_target_ms(base, _segment(zone="development"), "natural") == 1200
    assert boundary_pause_target_ms(base, _segment(), "off") == 0
    assert normalize_pacing_preset("unknown") == "natural"


def test_measure_wav_edge_silence_uses_rms_windows(tmp_path: Path) -> None:
    sample_rate = 48_000
    leading_seconds = 0.10
    speech_seconds = 0.20
    trailing_seconds = 0.15
    samples: list[int] = []
    samples.extend([0] * int(sample_rate * leading_seconds))
    for index in range(int(sample_rate * speech_seconds)):
        samples.append(int(12_000 * math.sin(2.0 * math.pi * 440.0 * index / sample_rate)))
    samples.extend([0] * int(sample_rate * trailing_seconds))
    wav_path = tmp_path / "edges.wav"
    with wave.open(str(wav_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    leading, trailing = measure_wav_edge_silence(wav_path)

    assert leading == 0.10
    assert trailing == 0.15
