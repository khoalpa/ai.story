from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from studio.audio_delivery_report import (
    inspect_audio_delivery,
    load_audio_delivery,
    parse_srt,
    read_audio_delivery_override,
    verify_artifact_hashes,
)


def _write_delivery(directory: Path, *, segment_count: int = 2) -> None:
    audio = directory / "story.wav"
    subtitle = directory / "story.srt"
    quality_path = directory / "story.audio_quality.json"
    audio.write_bytes(b"audio-data")
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nCâu một.\n\n"
        "2\n00:00:01,200 --> 00:00:02,000\nCâu hai.\n",
        encoding="utf-8",
    )
    quality = {
        "schema_version": 1,
        "profile": "narration",
        "target": {"integrated_lufs": -16, "true_peak_dbtp": -1.5, "loudness_range_lu": 9},
        "measured": {"integrated_lufs": -16, "true_peak_dbtp": -1.5, "loudness_range_lu": 2},
        "duration": {"source_seconds": 2, "output_seconds": 2, "delta_seconds": 0},
        "stream": {"codec_name": "pcm_s24le", "sample_rate": "48000", "channels": 2, "channel_layout": "stereo"},
        "segments": {"measured_count": segment_count, "measurements": [{"file": "a.wav", "integrated_lufs": -16}] * segment_count},
        "checks": {"integrated_loudness": True, "true_peak": True, "duration": True, "sample_rate": True, "channels": True},
        "passed": True,
    }
    quality_path.write_text(json.dumps(quality), encoding="utf-8")

    def artifact(path: Path, media_type: str) -> dict[str, object]:
        return {
            "path": path.name,
            "media_type": media_type,
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    handoff = {
        "schema_version": 1,
        "kind": "audio.video-handoff",
        "producer": "audio",
        "artifacts": {
            "audio": artifact(audio, "audio/wav"),
            "subtitle": artifact(subtitle, "application/x-subrip"),
            "quality_report": artifact(quality_path, "application/json"),
        },
    }
    (directory / "audio_video_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")


def test_parse_srt_builds_timed_cues() -> None:
    cues = parse_srt("1\n00:00:01,250 --> 00:00:03,000\nXin chào\n")
    assert cues[0].start_ms == 1250
    assert cues[0].duration_ms == 1750
    assert cues[0].text == "Xin chào"


def test_parse_srt_rejects_invalid_duration() -> None:
    with pytest.raises(ValueError, match="thời lượng"):
        parse_srt("1\n00:00:03,000 --> 00:00:01,000\nSai\n")


def test_uploaded_subtitle_uses_the_same_parser() -> None:
    from io import BytesIO

    cues = read_audio_delivery_override(
        BytesIO("1\n00:00:00,000 --> 00:00:01,000\nTệp tải lên\n".encode("utf-8")),
        "subtitle",
    )
    assert cues[0].text == "Tệp tải lên"


def test_delivery_loader_and_cross_checks_report_ready(tmp_path: Path) -> None:
    _write_delivery(tmp_path)
    data, statuses = load_audio_delivery(tmp_path)
    summary = inspect_audio_delivery(data, tmp_path)

    assert set(data) == {"handoff", "audio_quality", "subtitle"}
    assert set(statuses.values()) == {"Có dữ liệu"}
    assert summary["ready"] is True
    assert summary["cue_count"] == summary["segment_count"] == 2
    assert all(verify_artifact_hashes(summary["artifacts"]).values())


def test_delivery_cross_check_explains_segment_mismatch(tmp_path: Path) -> None:
    _write_delivery(tmp_path, segment_count=3)
    data, _statuses = load_audio_delivery(tmp_path)
    summary = inspect_audio_delivery(data, tmp_path)

    assert summary["ready"] is False
    assert any("2 câu" in issue and "3 segment" in issue for issue in summary["issues"])
