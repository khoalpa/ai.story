from __future__ import annotations

from pathlib import Path

from PIL import Image

from video.validation import inspect_video_image_readiness, resolve_slideshow_cover


def _write_image(path: Path, size: tuple[int, int] = (1080, 1920)) -> None:
    Image.new("RGB", size, color=(32, 64, 96)).save(path)


def _corrupt_png_checksum(path: Path) -> None:
    data = bytearray(path.read_bytes())
    idat = data.index(b"IDAT")
    data[idat + 4] ^= 0x01
    path.write_bytes(data)


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


def test_static_readiness_reports_png_checksum_error(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    _write_image(cover)
    _corrupt_png_checksum(cover)

    report = inspect_video_image_readiness(
        mode="static",
        aspect="9x16",
        cover=cover,
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


def test_cover_first_is_reported_and_excluded_from_scene_zone_warnings(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    cover = scenes_dir / "cover.png"
    _write_image(cover)
    _write_image(scenes_dir / "opening.png")

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="9x16",
        cover=cover,
        scenes_dir=scenes_dir,
        cover_first=True,
    )

    assert report.ready is True
    assert report.scene_count == 1
    assert [asset.role for asset in report.assets] == ["opening cover", "scene"]
    assert [path.name for path in report.unmatched_files] == []
    assert not any("cover.png" in warning for warning in report.warnings)


def test_cover_first_warns_when_cover_is_unavailable(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    _write_image(scenes_dir / "opening.png")

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="9x16",
        cover=tmp_path / "missing-cover.png",
        scenes_dir=scenes_dir,
        cover_first=True,
    )

    assert report.ready is True
    assert any("Opening cover was not found" in warning for warning in report.warnings)


def test_generated_cover_png_overrides_profile_default_cover(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    generated_cover = scenes_dir / "cover.png"
    _write_image(generated_cover)
    default_cover = tmp_path / "default_cover.png"
    _write_image(default_cover)

    resolved = resolve_slideshow_cover(
        default_cover,
        scenes_dir,
        cover_first=True,
    )

    assert resolved == generated_cover


def test_scene_png_is_excluded_from_readiness(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    _write_image(scenes_dir / "scene.png")
    _write_image(scenes_dir / "opening.png")

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="9x16",
        scenes_dir=scenes_dir,
    )

    assert report.scene_count == 1
    assert [path.name for path in report.unmatched_files] == []
    assert not any("do not match a known story zone" in warning for warning in report.warnings)


def test_intro_and_outro_cards_are_not_reported_as_story_zones(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    _write_image(scenes_dir / "intro.png")
    _write_image(scenes_dir / "opening.png")
    _write_image(scenes_dir / "outro.png")

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="9x16",
        scenes_dir=scenes_dir,
    )

    assert report.mapped_zones == ("opening",)
    assert "intro_card" not in report.missing_zones
    assert "outro_card" not in report.missing_zones
    assert [(asset.path.name, asset.role, asset.zone) for asset in report.assets] == [
        ("opening.png", "scene", "opening"),
        ("outro.png", "outro card", None),
    ]
    assert not any("intro_card" in warning or "outro_card" in warning for warning in report.warnings)


def test_readiness_assets_follow_slideshow_image_order(tmp_path: Path) -> None:
    scenes_dir = tmp_path / "scene_images"
    scenes_dir.mkdir()
    for name in (
        "farewell.png",
        "development.png",
        "greeting.png",
        "outro.png",
        "opening.png",
    ):
        _write_image(scenes_dir / name)

    report = inspect_video_image_readiness(
        mode="slideshow",
        aspect="9x16",
        scenes_dir=scenes_dir,
        outro_last=True,
    )

    assert [asset.path.name for asset in report.assets] == [
        "greeting.png",
        "opening.png",
        "development.png",
        "farewell.png",
        "outro.png",
    ]
