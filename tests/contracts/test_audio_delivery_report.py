from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from studio.audio_delivery_report import (
    _artifact_size_matches,
    _delivery_result_text,
    _quality_rows,
    inspect_audio_delivery,
    load_audio_delivery,
    parse_srt,
    read_audio_delivery_override,
    verify_artifact_hashes,
)


def test_missing_audio_quality_is_not_reported_as_failure() -> None:
    assert _delivery_result_text({}, False) == "Chưa kiểm định"
    assert _delivery_result_text({"passed": False}, False) == "Không đạt"


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


@pytest.mark.parametrize("size", ["invalid", [], {}, True, -1, 10.5, float("inf")])
def test_invalid_audio_size_is_reported_without_crashing(tmp_path: Path, size: object) -> None:
    _write_delivery(tmp_path)
    data, _ = load_audio_delivery(tmp_path)
    data["handoff"]["artifacts"]["audio"]["size_bytes"] = size
    summary = inspect_audio_delivery(data, tmp_path)
    assert summary["ready"] is False
    assert summary["artifacts"][0]["size_matches"] is False
    assert summary["issues"]


@pytest.mark.parametrize("size", [None, "", 3, "3"])
def test_optional_and_valid_artifact_sizes(tmp_path: Path, size: object) -> None:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"abc")
    assert _artifact_size_matches(path, size)
    assert not _artifact_size_matches(None, size)
    assert not _artifact_size_matches(tmp_path / "missing.wav", size)


def test_artifact_size_stat_failure_is_not_a_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def inaccessible(*args: object, **kwargs: object) -> None:
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "stat", inaccessible)
    assert not _artifact_size_matches(tmp_path / "audio.wav", 3)


@pytest.mark.parametrize(("measured", "expected"), [
    (20, "Không đạt"), (9, "Đạt"), (2, "Đạt"),
    (None, "Chưa xác minh"), ("invalid", "Chưa xác minh"),
    (float("nan"), "Chưa xác minh"), (float("inf"), "Chưa xác minh"),
])
@pytest.mark.parametrize("integrated_passed", [True, False])
def test_loudness_range_uses_its_own_measurement(measured: object, expected: str, integrated_passed: bool) -> None:
    rows = _quality_rows({
        "target": {"loudness_range_lu": 9},
        "measured": {"loudness_range_lu": measured},
        "checks": {"integrated_loudness": integrated_passed},
    })
    assert next(row for row in rows if row["Chỉ số"] == "Loudness range")["Kết quả"] == expected


@pytest.mark.parametrize("checks", [{"true_peak": False}, {"true_peak": "false"}, {"true_peak": 1}, {}])
def test_audio_readiness_requires_passing_checks(tmp_path: Path, checks: dict) -> None:
    _write_delivery(tmp_path)
    data, _ = load_audio_delivery(tmp_path)
    data["audio_quality"]["checks"] = checks
    summary = inspect_audio_delivery(data, tmp_path)
    assert summary["ready"] is False
    assert summary["passed"] is False
    assert summary["issues"]


@pytest.mark.parametrize("duration", ["invalid", [], {}, True, -1, "", float("nan"), float("inf")])
def test_invalid_audio_duration_blocks_readiness(tmp_path: Path, duration: object) -> None:
    from io import BytesIO

    from studio.audio_delivery_report import format_duration

    _write_delivery(tmp_path)
    data, _ = load_audio_delivery(tmp_path)
    data["audio_quality"]["duration"]["output_seconds"] = duration
    data["audio_quality"] = read_audio_delivery_override(
        BytesIO(json.dumps(data["audio_quality"]).encode()), "audio_quality",
    )
    summary = inspect_audio_delivery(data, tmp_path)
    assert summary["ready"] is False
    assert any("duration.output_seconds" in issue for issue in summary["issues"])
    assert format_duration(duration) == "—"


@pytest.mark.parametrize(("seconds", "expected"), [(None, "0:00"), (0, "0:00"), (90, "1:30"), (3661, "1:01:01")])
def test_valid_duration_format_is_preserved(seconds: int | None, expected: str) -> None:
    from studio.audio_delivery_report import format_duration

    assert format_duration(seconds) == expected
