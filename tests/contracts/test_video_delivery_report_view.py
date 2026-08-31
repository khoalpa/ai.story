from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from studio.video_delivery_report import (
    VIDEO_PREVIEW_STYLE,
    apply_video_report_override,
    build_video_delivery_summary,
    discover_video_report_names,
    load_video_deliveries,
    video_report_identity,
)


def test_video_preview_uses_one_landscape_height_for_every_variant() -> None:
    assert 'video[data-testid="stVideo"]' in VIDEO_PREVIEW_STYLE
    assert "aspect-ratio: 16 / 9" in VIDEO_PREVIEW_STYLE
    assert "object-fit: contain" in VIDEO_PREVIEW_STYLE
    source = Path("studio/video_delivery_report.py").read_text(encoding="utf-8")
    assert 'st.container(key="story_video_preview")' in source


def _result(video_name: str, size: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "video.result-manifest",
        "producer": "video",
        "artifacts": {"video": {"path": video_name, "size_bytes": size}},
        "metadata": {"duration_seconds": 10, "resolution": "1920x1080"},
    }


def _quality(*, passed: bool = True) -> dict[str, object]:
    return {
        "schema_version": 1,
        "measured": {"integrated_lufs": -16, "true_peak_dbtp": -1.5},
        "duration": {"container_seconds": 10, "delta_seconds": 0},
        "video_stream": {"width": 1920, "height": 1080, "codec_name": "h264", "avg_frame_rate": "24/1"},
        "audio_stream": {"codec_name": "aac"},
        "subtitle": {"present": True, "timing_ok": True, "long_lines": []},
        "checks": {"decode": passed, "visual_ssim": passed},
        "passed": passed,
    }


def test_video_report_names_support_arbitrary_variants() -> None:
    assert video_report_identity("youtube_short.result.json") == ("youtube_short", "result")
    assert video_report_identity("youtube_short.video_quality.json") == ("youtube_short", "quality")


def test_loader_pairs_result_and_quality_and_reports_ready(tmp_path: Path) -> None:
    video = tmp_path / "video_custom.mp4"
    video.write_bytes(b"video")
    (tmp_path / "video_custom.result.json").write_text(json.dumps(_result(video.name, video.stat().st_size)), encoding="utf-8")
    (tmp_path / "video_custom.video_quality.json").write_text(json.dumps(_quality()), encoding="utf-8")

    variants, statuses = load_video_deliveries(tmp_path)
    summaries = build_video_delivery_summary(variants, tmp_path)

    assert set(variants["video_custom"]) == {"result", "quality"}
    assert statuses["video_custom.result.json"] == "Có dữ liệu"
    assert summaries[0]["ready"] is True


def test_discovery_includes_defaults_and_new_variants(tmp_path: Path) -> None:
    (tmp_path / "social_square.result.json").write_text("{}", encoding="utf-8")
    names = discover_video_report_names(tmp_path)
    assert "video_landscape.result.json" in names
    assert "video_portrait.video_quality.json" in names
    assert "social_square.result.json" in names


def test_uploaded_report_replaces_matching_variant() -> None:
    variants: dict[str, dict[str, object]] = {}
    payload = BytesIO(json.dumps(_quality(passed=False)).encode("utf-8"))
    variant, kind = apply_video_report_override(variants, payload, "video_portrait.video_quality.json")
    assert (variant, kind) == ("video_portrait", "quality")
    assert variants[variant][kind]["passed"] is False
