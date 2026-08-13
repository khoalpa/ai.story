from __future__ import annotations

from pathlib import Path

import pytest

from video.slideshow_concat import build_slideshow_segments, prepend_cover_segment
from video.zone_timeline import ZoneSegment, estimate_zone_duration
from video.validation import build_zone_slideshow_images


def test_cover_replaces_start_of_regular_slideshow_without_extending_it(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    scenes = [tmp_path / "opening.png", tmp_path / "development.png"]
    base = build_slideshow_segments(scenes, 10.0, match_audio=False)

    result = prepend_cover_segment(base, cover, 3.0)

    assert [(segment.image.name, segment.start, segment.end) for segment in result] == [
        ("cover.png", 0.0, 3.0),
        ("opening.png", 3.0, 10.0),
        ("development.png", 10.0, 20.0),
    ]
    assert estimate_zone_duration(result) == estimate_zone_duration(base) == 20.0


def test_cover_can_consume_multiple_short_segments_without_duplicates(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    base = [
        ZoneSegment("greeting", tmp_path / "greeting.png", 0.0, 1.0),
        ZoneSegment("opening", tmp_path / "opening.png", 1.0, 2.5),
        ZoneSegment("development", tmp_path / "development.png", 2.5, 8.0),
    ]

    result = prepend_cover_segment(base, cover, 3.0)

    assert [(segment.zone, segment.start, segment.end) for segment in result] == [
        ("cover", 0.0, 3.0),
        ("development", 3.0, 8.0),
    ]
    assert estimate_zone_duration(result) == 8.0


def test_missing_cover_selection_keeps_existing_timeline(tmp_path: Path) -> None:
    base = [ZoneSegment("opening", tmp_path / "opening.png", 0.0, 5.0)]

    assert prepend_cover_segment(base, None, 3.0) == base


def test_cover_duration_must_be_positive(tmp_path: Path) -> None:
    base = [ZoneSegment("opening", tmp_path / "opening.png", 0.0, 5.0)]

    with pytest.raises(ValueError, match="cover_duration must be > 0"):
        prepend_cover_segment(base, tmp_path / "cover.png", 0.0)


def test_audio_matching_still_controls_total_timeline_duration(tmp_path: Path) -> None:
    scenes = [tmp_path / "opening.png", tmp_path / "ending.png"]

    result = build_slideshow_segments(
        scenes,
        10.0,
        audio_duration=35.0,
        match_audio=True,
        audio_match_epsilon=0.2,
    )

    assert result[-1].end == pytest.approx(35.2)


def test_scene_and_intro_png_are_excluded_from_zone_images(tmp_path: Path) -> None:
    images = [
        tmp_path / "opening.png",
        tmp_path / "scene.png",
        tmp_path / "ending.png",
    ]

    ordered = build_zone_slideshow_images(images)

    assert [image.name for image in ordered] == ["opening.png", "ending.png"]
