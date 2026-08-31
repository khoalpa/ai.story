from __future__ import annotations

from pathlib import Path

from PIL import Image

from studio.story_images import (
    EXPECTED_IMAGE_STEMS,
    discover_story_images,
    image_for_zone,
    image_metadata,
    inspect_story_images,
    thumbnail_bytes,
)


def _image(path: Path, size: tuple[int, int] = (1200, 675)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (24, 48, 72)).save(path)


def test_discovery_maps_zone_images_for_both_aspects(tmp_path: Path) -> None:
    _image(tmp_path / "landscape" / "opening.png")
    _image(tmp_path / "portrait" / "opening.png", (675, 1200))
    catalog = discover_story_images(tmp_path)
    assert image_for_zone(catalog, "landscape", "OPENING") == (tmp_path / "landscape" / "opening.png").resolve()
    assert image_for_zone(catalog, "portrait", "OPENING") == (tmp_path / "portrait" / "opening.png").resolve()


def test_image_summary_reports_missing_expected_assets(tmp_path: Path) -> None:
    _image(tmp_path / "landscape" / "cover.png")
    summary = inspect_story_images(tmp_path)
    assert summary["landscape"]["count"] == 1
    assert len(summary["landscape"]["missing"]) == len(EXPECTED_IMAGE_STEMS) - 1
    assert summary["portrait"]["count"] == 0


def test_thumbnail_is_resized_and_metadata_keeps_original_dimensions(tmp_path: Path) -> None:
    path = tmp_path / "landscape" / "cover.png"
    _image(path, (1600, 900))
    preview = thumbnail_bytes(path, max_width=320)
    preview_path = tmp_path / "preview.webp"
    preview_path.write_bytes(preview)
    with Image.open(preview_path) as image:
        assert image.width == 320
        assert image.height == 180
    assert image_metadata(path)["width"] == 1600


def test_landscape_and_portrait_framed_thumbnails_have_equal_display_height(
    tmp_path: Path,
) -> None:
    landscape = tmp_path / "landscape.png"
    portrait = tmp_path / "portrait.png"
    _image(landscape, (1600, 900))
    _image(portrait, (900, 1600))
    landscape_preview = tmp_path / "landscape.webp"
    portrait_preview = tmp_path / "portrait.webp"
    landscape_preview.write_bytes(thumbnail_bytes(landscape, max_width=480, frame_ratio=(16, 9)))
    portrait_preview.write_bytes(thumbnail_bytes(portrait, max_width=480, frame_ratio=(16, 9)))
    with Image.open(landscape_preview) as landscape_image, Image.open(portrait_preview) as portrait_image:
        assert landscape_image.size == portrait_image.size == (480, 270)


def test_related_views_use_shared_thumbnail_component() -> None:
    overview = Path("studio/overview.py").read_text(encoding="utf-8")
    story = Path("studio/story_report.py").read_text(encoding="utf-8")
    video = Path("studio/video_delivery_report.py").read_text(encoding="utf-8")
    assert "render_aspect_cover_gallery" in overview
    assert "image_for_zone" in story
    assert "render_image_thumbnail" in video
