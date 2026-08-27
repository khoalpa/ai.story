from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from audio.adapters.ffmpeg_audio_mixer import (
    get_audio_duration_seconds,
    write_audio_quality_report,
)
from audio.runtime_checks import validate_runtime_executables
from audio.services.subtitle import write_srt_from_timeline


def test_real_audio_fixture_duration_subtitle_and_quality_report(tmp_path: Path) -> None:
    try:
        binaries = validate_runtime_executables("ffmpeg", "ffprobe")
    except Exception as exc:
        pytest.skip(f"FFmpeg runtime is unavailable: {exc}")

    audio_path = tmp_path / "fixture.wav"
    subprocess.run(
        [
            binaries.ffmpeg_exe,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
            "-af",
            "loudnorm=I=-16:LRA=9:TP=-1.5",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    duration = get_audio_duration_seconds(audio_path, binaries.ffprobe_exe)
    assert duration == pytest.approx(1.0, abs=0.05)

    srt_path = tmp_path / "fixture.srt"
    write_srt_from_timeline(
        [{"start": 0.0, "end": duration, "text": "Âm thanh kiểm thử."}],
        srt_path,
    )
    subtitle = srt_path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,000" in subtitle
    assert "Âm thanh kiểm thử." in subtitle

    report_path, report = write_audio_quality_report(
        audio_path,
        source_duration_seconds=1.0,
        ffmpeg_exe=binaries.ffmpeg_exe,
        ffprobe_exe=binaries.ffprobe_exe,
        loudness_profile="narration",
        expected_sample_rate=48000,
        expected_channels=2,
    )

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["audio_file"] == str(audio_path.resolve())
    assert report["checks"]["duration"] is True
    assert report["checks"]["sample_rate"] is True
    assert report["checks"]["channels"] is True
    assert report["measured"]["integrated_lufs"] == pytest.approx(-16.0, abs=1.0)
