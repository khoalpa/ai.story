from __future__ import annotations

from pathlib import Path

from PIL import Image

from video.validation import inspect_video_image_readiness


def _write_image(path: Path, size: tuple[int, int] = (1080, 1920)) -> None:
    Image.new("RGB", size, color=(32, 64, 96)).save(path)


def test_static_cover_readiness_accepts_valid_image(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    _write_image(cover)

    report = inspect_video_image_readiness(
        mode="static",
        aspect="9x16",
        cover=cover,
    )

    assert report.ready is True
    assert report.errors == []
    assert report.assets[0].width == 1080
    assert report.assets[0].height == 1920


def test_slideshow_readiness_rejects_corrupt_scene_image(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    (scenes_dir / "opening.png").write_bytes(b"not an image")

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="9x16",
        scenes_dir=scenes_dir,
    )

    assert report.ready is False
    assert any("cannot be opened" in message for message in report.errors)


def test_slideshow_readiness_warns_for_small_or_unmapped_images(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    _write_image(scenes_dir / "opening.png", size=(300, 300))
    _write_image(scenes_dir / "custom_scene.png")
    _write_image(scenes_dir / "ignored.webp")

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="9x16",
        scenes_dir=scenes_dir,
    )

    assert report.ready is True
    assert report.scene_count == 2
    assert report.mapped_zones == ("opening",)
    assert [path.name for path in report.unmatched_files] == ["custom_scene.png"]
    assert any("smaller than recommended" in message for message in report.warnings)
    assert any("unsupported" in message for message in report.warnings)
    assert any("do not match a known story zone" in message for message in report.warnings)
