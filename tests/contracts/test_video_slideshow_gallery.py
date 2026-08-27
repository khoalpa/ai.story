from pathlib import Path

from video.gui.tabs import _build_slideshow_gallery_items
from video.zone_timeline import ZoneSegment


def _touch_images(root: Path, names: tuple[str, ...]) -> None:
    for name in names:
        (root / name).write_bytes(b"image")


def test_gallery_keeps_images_clipped_out_of_effective_timeline(tmp_path: Path) -> None:
    names = (
        "cover.png",
        "greeting.png",
        "opening.png",
        "introduction.png",
        "development.png",
        "climax.png",
        "falling.png",
        "ending.png",
        "farewell.png",
        "outro.png",
    )
    _touch_images(tmp_path, names)
    segments = [
        ZoneSegment("cover", tmp_path / "cover.png", 0.0, 7.0),
        ZoneSegment("end_screen", tmp_path / "outro.png", 7.0, 16.0),
    ]

    items = _build_slideshow_gallery_items(
        {"scenes_dir": tmp_path, "cover": tmp_path / "cover.png"},
        {"cover_first": True, "outro_last": True},
        segments,
    )

    assert [image.name for image, _ in items] == list(names)
    assert [len(image_segments) for _, image_segments in items] == [1] + [0] * 8 + [1]


def test_gallery_respects_disabled_endpoints(tmp_path: Path) -> None:
    _touch_images(tmp_path, ("cover.png", "greeting.png", "outro.png"))

    items = _build_slideshow_gallery_items(
        {"scenes_dir": tmp_path, "cover": tmp_path / "cover.png"},
        {"cover_first": False, "outro_last": False},
        [],
    )

    assert [image.name for image, _ in items] == ["greeting.png"]
