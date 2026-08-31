"""Slideshow gallery data and endpoint presentation helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from video.validation import (
    build_zone_slideshow_images,
    collect_scene_images,
    resolve_slideshow_cover,
    resolve_slideshow_outro,
)
from video.zone_timeline import ZoneSegment


def _format_timeline_timestamp(seconds: float | int) -> str:
    """Format a slideshow timeline position as a fixed-width HH:MM:SS value."""
    try:
        total_seconds = max(0, int(round(float(seconds))))
    except (TypeError, ValueError, OverflowError):
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _build_slideshow_gallery_items(
    inputs: dict[str, Any],
    settings: dict[str, Any],
    segments: list[ZoneSegment],
) -> list[tuple[Path, list[ZoneSegment]]]:
    """List every configured image, including ones clipped out by endpoint timing."""
    scenes_dir = inputs.get("scenes_dir")
    if scenes_dir is None or not Path(scenes_dir).is_dir():
        return []

    scene_root = Path(scenes_dir)
    cover = resolve_slideshow_cover(
        inputs.get("cover"),
        scene_root,
        cover_first=bool(settings.get("cover_first", True)),
    )
    outro = resolve_slideshow_outro(
        scene_root,
        outro_last=bool(settings.get("outro_last", True)),
    )
    scene_images = build_zone_slideshow_images(collect_scene_images(scene_root))
    endpoint_paths = {
        path.resolve(strict=False)
        for path in (cover, outro)
        if path is not None and path.is_file()
    }
    scene_images = [
        image for image in scene_images if image.resolve(strict=False) not in endpoint_paths
    ]

    ordered_images: list[Path] = []
    if cover is not None and cover.is_file():
        ordered_images.append(cover)
    ordered_images.extend(scene_images)
    if outro is not None and outro.is_file():
        ordered_images.append(outro)

    segments_by_image: dict[Path, list[ZoneSegment]] = {}
    for segment in segments:
        key = segment.image.resolve(strict=False)
        segments_by_image.setdefault(key, []).append(segment)
    return [
        (image, segments_by_image.get(image.resolve(strict=False), []))
        for image in ordered_images
    ]


def _render_slideshow_endpoint(
    *,
    title: str,
    status: str,
    message: str,
    image_path: Path | None,
    image_caption: str,
    details: dict[str, Any],
) -> None:
    """Render opening and ending settings with the same visual structure."""
    st.subheader(title)
    getattr(st, status)(message)
    if image_path is not None and image_path.is_file():
        image_column, details_column = st.columns([1, 2], gap="large")
        with image_column:
            st.image(str(image_path), caption=image_caption, width=320)
        with details_column:
            st.write(details)
    else:
        st.write(details)
