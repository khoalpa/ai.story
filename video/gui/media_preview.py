"""Resolved media and slideshow previews for the Video workspace."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

import streamlit as st

from video.ffmpeg_runner import get_media_duration_seconds
from video.gui.panel_utils import render_json_summary_expander
from video.gui.slideshow_gallery import (
    _build_slideshow_gallery_items,
    _format_timeline_timestamp,
    _render_slideshow_endpoint,
)
from video.gui.user_messages import show_missing_input
from video.scene_timeline import build_scene_segments, resolve_slideshow_timeline_mode
from video.slideshow_concat import (
    append_outro_segment,
    build_slideshow_segments,
    prepend_cover_segment,
)
from video.validation import (
    ImageReadinessReport,
    build_zone_slideshow_images,
    collect_scene_images,
    resolve_slideshow_cover,
    resolve_slideshow_outro,
)
from video.zone_timeline import ZoneSegment, build_zone_segments


def _build_test_slideshow_segments(
    inputs: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[list[ZoneSegment], Optional[str]]:
    scenes_dir = inputs.get("scenes_dir")
    if scenes_dir is None or not Path(scenes_dir).is_dir():
        return [], None

    cover = resolve_slideshow_cover(
        inputs.get("cover"),
        Path(scenes_dir),
        cover_first=bool(settings.get("cover_first", True)),
    )
    outro = resolve_slideshow_outro(
        Path(scenes_dir),
        outro_last=bool(settings.get("outro_last", True)),
    )
    try:
        timeline_mode = resolve_slideshow_timeline_mode(
            "zone" if settings.get("zone_aware_slideshow") and settings.get("slideshow_timeline_mode", "auto") == "auto" else str(settings.get("slideshow_timeline_mode", "auto")),
            inputs.get("visual_plan_json"),
        )
        if timeline_mode in {"zone", "scene"}:
            story_json = inputs.get("story_json")
            subtitle = inputs.get("subtitle")
            if story_json and subtitle and Path(story_json).is_file() and Path(subtitle).is_file():
                if timeline_mode == "scene":
                    visual_plan = inputs.get("visual_plan_json")
                    if visual_plan is None:
                        return [], "Scene-aware slideshow requires visual_plan.json."
                    segments = build_scene_segments(
                        timeline_json=Path(story_json),
                        visual_plan_json=Path(visual_plan),
                        subtitle=Path(subtitle),
                        scenes_dir=Path(scenes_dir),
                    )
                else:
                    segments = build_zone_segments(
                        timeline_json=Path(story_json),
                        subtitle=Path(subtitle),
                        scenes_dir=Path(scenes_dir),
                    )
                segments = prepend_cover_segment(
                    segments,
                    cover if cover and Path(cover).is_file() else None,
                    float(settings.get("cover_duration", 3.0)),
                )
                return append_outro_segment(
                    segments,
                    outro,
                    float(settings.get("outro_duration", 5.0)),
                ), None

        images = build_zone_slideshow_images(collect_scene_images(Path(scenes_dir)))
        if cover is not None and Path(cover).is_file():
            cover_resolved = Path(cover).resolve(strict=False)
            images = [
                image for image in images if image.resolve(strict=False) != cover_resolved
            ]
        if outro is not None:
            outro_resolved = outro.resolve(strict=False)
            images = [
                image for image in images if image.resolve(strict=False) != outro_resolved
            ]
        if not images:
            return [], None
        audio = inputs.get("audio")
        audio_duration = (
            get_media_duration_seconds(Path(audio))
            if audio and Path(audio).is_file()
            else None
        )
        segments = build_slideshow_segments(
            images,
            float(settings.get("duration_per_image", 60.0)),
            audio_duration=audio_duration,
            match_audio=bool(settings.get("slideshow_match_audio", True)),
            audio_match_epsilon=float(settings.get("audio_match_epsilon", 0.2)),
        )
        segments = prepend_cover_segment(
            segments,
            cover if cover and Path(cover).is_file() else None,
            float(settings.get("cover_duration", 3.0)),
        )
        return append_outro_segment(
            segments,
            outro,
            float(settings.get("outro_duration", 5.0)),
        ), None
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return [], str(exc)


def _render_slideshow_order_gallery(
    inputs: dict[str, Any],
    settings: dict[str, Any],
) -> None:
    segments, error = _build_test_slideshow_segments(inputs, settings)
    st.subheader("Slideshow image order")
    if error:
        st.warning(f"Could not build the exact slideshow timeline: {error}")
    gallery_items = _build_slideshow_gallery_items(inputs, settings, segments)
    if not gallery_items:
        st.info("No slideshow images are available yet.")
        return

    st.caption(
        f"Configured image order: {len(gallery_items)} image(s); "
        f"{len(segments)} effective timeline segment(s)."
    )
    for row_start in range(0, len(gallery_items), 4):
        columns = st.columns(4)
        for offset, (image_path, image_segments) in enumerate(
            gallery_items[row_start : row_start + 4]
        ):
            index = row_start + offset + 1
            columns[offset].image(str(image_path), width=160)
            if image_segments:
                timing = ", ".join(
                    f"{segment.zone} · {_format_timeline_timestamp(segment.start)}"
                    f"–{_format_timeline_timestamp(segment.end)}"
                    for segment in image_segments
                )
            else:
                timing = "not visible with current timing"
            columns[offset].caption(f"#{index:02d} {image_path.name}\n{timing}")


def _render_test_media_inputs(inputs: dict[str, Any], summary: dict[str, Any]) -> None:
    """Render resolved test inputs around the audio preview without raw JSON blocks."""
    st.subheader("Audio & resolved inputs")
    audio_path = inputs.get("audio")
    if audio_path and Path(audio_path).is_file():
        st.audio(str(audio_path))
    else:
        st.info("No playable audio input is available yet.")

    rows = []
    for label, key, source_key in (
        ("Audio", "audio", None),
        ("Subtitle", "subtitle", None),
        ("Timeline JSON", "story_json", None),
        ("Video output", "output", None),
        ("Cover", "cover", "cover_source"),
        ("Scenes", "scenes_dir", "scenes_source"),
    ):
        value = inputs.get(key)
        path = Path(value) if value else None
        exists = bool(path and path.exists())
        rows.append(
            {
                "input": label,
                "status": "ready" if exists else ("pending" if key == "output" else "missing"),
                "file": path.name if path else "",
                "source": str(summary.get(source_key) or "") if source_key else "",
                "path": str(path or ""),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True, height=250)


def render_video_preview(
    settings: dict[str, Any], *, inputs: dict[str, Any],
    render_readiness: Callable[[ImageReadinessReport], None],
) -> None:
    summary = dict(inputs.get("summary") or {})

    if inputs.get("errors"):
        for err in inputs["errors"]:
            show_missing_input("video input", hint=err, actions=["Check the selected source again in the Inputs tab."])
    else:
        st.success("Current video inputs resolve successfully.")

    _render_test_media_inputs(inputs, summary)

    st.subheader("Mức sẵn sàng của hình ảnh")
    render_readiness(inputs["image_readiness"])

    is_slideshow = str(settings.get("mode") or "") == "slideshow"
    scenes_dir = inputs.get("scenes_dir")
    if is_slideshow and scenes_dir and Path(scenes_dir).is_dir():
        _render_slideshow_order_gallery(inputs, settings)

    if is_slideshow:
        cover_first = bool(settings.get("cover_first", True))
        cover_duration = float(settings.get("cover_duration", 3.0))
        cover_path = Path(inputs["cover"]) if inputs.get("cover") else None
        cover_available = bool(cover_path and cover_path.is_file())
        if not cover_first:
            opening_status = "info"
            opening_message = "Cover-first is disabled. The video will start with the first scene image."
        elif cover_available and cover_path is not None:
            opening_status = "success"
            opening_message = (
                f"Cover-first is active: {cover_path.name} will be shown for "
                f"{cover_duration:g} seconds without extending the MP4 duration."
            )
        else:
            opening_status = "warning"
            opening_message = (
                "Cover-first is enabled, but the selected cover is unavailable. "
                "The video will start with the first scene image."
            )
        _render_slideshow_endpoint(
            title="Slideshow opening",
            status=opening_status,
            message=opening_message,
            image_path=cover_path if cover_first and cover_available else None,
            image_caption=f"Opening cover: {cover_path.name}" if cover_path else "Opening cover",
            details={
                "cover_first": cover_first,
                "cover_duration_seconds": cover_duration,
                "cover_path": str(cover_path or ""),
                "effective_first_image": (
                    str(cover_path)
                    if cover_first and cover_available
                    else str(inputs.get("scenes_dir") or "")
                ),
            },
        )

        outro_last = bool(settings.get("outro_last", True))
        outro_duration = float(settings.get("outro_duration", 5.0))
        outro_path = resolve_slideshow_outro(
            inputs.get("scenes_dir"),
            outro_last=outro_last,
        )
        if not outro_last:
            ending_status = "info"
            ending_message = "End screen is disabled. The video will keep its final scene."
        elif outro_path is not None:
            ending_status = "success"
            ending_message = (
                f"End screen is active: {outro_path.name} will be shown for "
                f"the final {outro_duration:g} seconds without extending the MP4 duration."
            )
        else:
            ending_status = "warning"
            ending_message = (
                "End screen is enabled, but outro.png was not found. "
                "The video will keep its final scene."
            )
        _render_slideshow_endpoint(
            title="Slideshow ending",
            status=ending_status,
            message=ending_message,
            image_path=outro_path,
            image_caption=f"End screen: {outro_path.name}" if outro_path else "End screen",
            details={
                "outro_last": outro_last,
                "outro_duration_seconds": outro_duration,
                "outro_path": str(outro_path or ""),
                "effective_last_image": str(outro_path or ""),
            },
        )

    cover_path = inputs.get("cover")
    if not is_slideshow and cover_path and Path(cover_path).is_file():
        cover_caption = Path(cover_path).name
        st.image(str(cover_path), caption=cover_caption, width=240)

    render_json_summary_expander("Test input summary", summary, expanded=False)
