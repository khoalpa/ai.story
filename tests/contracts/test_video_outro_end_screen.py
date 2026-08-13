from pathlib import Path

import pytest
from PIL import Image

from video.slideshow_concat import append_outro_segment
from video.zone_timeline import ZoneSegment
from video.validation import inspect_video_image_readiness, resolve_slideshow_outro


def _segment(image: Path, start: float, end: float) -> ZoneSegment:
    return ZoneSegment(zone=image.stem, image=image, start=start, end=end)


def _write_image(path: Path) -> None:
    Image.new("RGB", (1920, 1080), color=(20, 30, 40)).save(path)


def test_outro_replaces_timeline_tail_without_extending_video(tmp_path: Path) -> None:
    first = tmp_path / "opening.png"
    second = tmp_path / "ending.png"
    outro = tmp_path / "outro.png"

    result = append_outro_segment(
        [_segment(first, 0.0, 8.0), _segment(second, 8.0, 12.0)],
        outro,
        5.0,
    )

    assert [
        (segment.zone, segment.image.name, segment.start, segment.end)
        for segment in result
    ] == [
        ("opening", "opening.png", 0.0, 7.0),
        ("end_screen", "outro.png", 7.0, 12.0),
    ]


def test_outro_can_fill_a_short_video(tmp_path: Path) -> None:
    result = append_outro_segment(
        [_segment(tmp_path / "scene.png", 0.0, 3.0)],
        tmp_path / "outro.png",
        5.0,
    )

    assert [(item.zone, item.start, item.end) for item in result] == [
        ("end_screen", 0.0, 3.0)
    ]


def test_outro_duration_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outro_duration must be > 0"):
        append_outro_segment(
            [_segment(tmp_path / "scene.png", 0.0, 3.0)],
            tmp_path / "outro.png",
            0.0,
        )


def test_outro_is_auto_detected_and_reported_as_end_screen(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "images"
    scenes_dir.mkdir()
    _write_image(scenes_dir / "opening.png")
    outro = scenes_dir / "outro.png"
    _write_image(outro)

    assert resolve_slideshow_outro(scenes_dir, outro_last=True) == outro

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="16x9",
        scenes_dir=scenes_dir,
        outro_last=True,
    )

    assert report.ready is True
    assert report.scene_count == 1
    assert [asset.role for asset in report.assets] == ["scene", "end screen"]
    assert not any("outro.png" in warning for warning in report.warnings)


def test_missing_outro_is_a_non_blocking_warning(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "images"
    scenes_dir.mkdir()
    _write_image(scenes_dir / "opening.png")

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="16x9",
        scenes_dir=scenes_dir,
        outro_last=True,
    )

    assert report.ready is True
    assert any("outro.png was not found" in warning for warning in report.warnings)
