from __future__ import annotations

import json
from pathlib import Path

import pytest

from video.slideshow_concat import write_timeline_concat_list
from video.story_zone_timeline import build_story_zone_segments, normalize_story_zone


def _write_story(path: Path, script: list[dict[str, str]]) -> None:
    path.write_text(json.dumps({"script": script}, ensure_ascii=False), encoding="utf-8")


def _write_srt(path: Path, entries: list[tuple[str, str, str]]) -> None:
    lines: list[str] = []
    for idx, (start, end, text) in enumerate(entries, start=1):
        lines.extend([str(idx), f"{start} --> {end}", text, ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def test_normalize_story_zone_accepts_vietnamese_labels() -> None:
    assert normalize_story_zone("L\u1edcI CH\u00c0O") == "greeting"
    assert normalize_story_zone("M\u1ede \u0110\u1ea6U") == "opening"
    assert normalize_story_zone("TRI\u1ec2N KHAI") == "development"
    assert normalize_story_zone("T\u1ea0M BI\u1ec6T") == "farewell"


def test_build_story_zone_segments_uses_story_json_srt_and_zone_images(tmp_path: Path) -> None:
    story_json = tmp_path / "story.json"
    subtitle = tmp_path / "story.srt"
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    greeting = scenes_dir / "greeting.png"
    opening = scenes_dir / "opening.png"
    greeting.write_bytes(b"")
    opening.write_bytes(b"")

    _write_story(
        story_json,
        [
            {"zone": "L\u1edcI CH\u00c0O", "text": "Hello listener."},
            {"zone": "M\u1ede TRUY\u1ec6N", "text": "The door opened."},
            {"zone": "M\u1ede TRUY\u1ec6N", "text": "Rain entered the room."},
        ],
    )
    _write_srt(
        subtitle,
        [
            ("00:00:00,000", "00:00:02,000", "Hello listener."),
            ("00:00:02,000", "00:00:05,000", "The door opened."),
            ("00:00:05,000", "00:00:09,500", "Rain entered the room."),
        ],
    )

    segments = build_story_zone_segments(
        story_json=story_json,
        subtitle=subtitle,
        scenes_dir=scenes_dir,
    )

    assert [(segment.zone, segment.duration, segment.image) for segment in segments] == [
        ("greeting", 2.0, greeting),
        ("opening", 7.5, opening),
    ]


def test_build_story_zone_segments_rejects_zero_timestamp_srt(tmp_path: Path) -> None:
    story_json = tmp_path / "story.json"
    subtitle = tmp_path / "story.srt"
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    (scenes_dir / "greeting.png").write_bytes(b"")
    _write_story(story_json, [{"zone": "GREETING", "text": "Hello listener."}])
    _write_srt(
        subtitle,
        [("00:00:00,000", "00:00:00,000", "Hello listener.")],
    )

    with pytest.raises(ValueError, match="SRT timestamps"):
        build_story_zone_segments(
            story_json=story_json,
            subtitle=subtitle,
            scenes_dir=scenes_dir,
        )


def test_write_timeline_concat_list_writes_segment_durations(tmp_path: Path) -> None:
    story_json = tmp_path / "story.json"
    subtitle = tmp_path / "story.srt"
    scenes_dir = tmp_path / "scene_images"
    concat = tmp_path / "story.ffconcat"
    scenes_dir.mkdir()
    (scenes_dir / "greeting.png").write_bytes(b"")
    _write_story(story_json, [{"zone": "GREETING", "text": "Hello listener."}])
    _write_srt(
        subtitle,
        [("00:00:00,000", "00:00:03,250", "Hello listener.")],
    )

    segments = build_story_zone_segments(
        story_json=story_json,
        subtitle=subtitle,
        scenes_dir=scenes_dir,
    )
    write_timeline_concat_list(segments, concat)

    content = concat.read_text(encoding="utf-8")
    assert content.startswith("ffconcat version 1.0")
    assert "duration 3.250000" in content
    assert content.rstrip().endswith("greeting.png'")
