"""Build an image timeline from the authoritative SCENE visual plan."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from video.zone_timeline import (
    ZoneSegment,
    load_timeline_script,
    match_script_to_srt,
    parse_srt,
)

SCENE_IMAGE_PATTERN = re.compile(r"^scene_(\d{4})\.png$", re.IGNORECASE)


def _resolved_mode(plan: dict[str, Any]) -> str:
    return str(
        plan.get("resolved_image_generation_mode")
        or plan.get("resolved_mode")
        or plan.get("image_generation_mode")
        or plan.get("mode")
        or ""
    ).upper()


def _scene_assets(plan: dict[str, Any]) -> list[dict[str, Any]]:
    assets = plan.get("assets")
    if not isinstance(assets, list):
        raise ValueError("visual_plan.json must contain an assets array.")
    selected = [asset for asset in assets if isinstance(asset, dict) and str(asset.get("role", "")).upper() == "SCENE"]
    if not selected:
        raise ValueError("visual_plan.json contains no role=SCENE assets.")
    return selected


def _asset_basename(asset: dict[str, Any]) -> str:
    raw = asset.get("basename") or asset.get("file_name") or asset.get("filename") or asset.get("path")
    return Path(str(raw or "")).name


def build_scene_segments(
    *,
    timeline_json: Path,
    visual_plan_json: Path,
    subtitle: Path,
    scenes_dir: Path,
) -> list[ZoneSegment]:
    plan = json.loads(Path(visual_plan_json).read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("visual_plan.json root must be an object.")
    if _resolved_mode(plan) != "SCENE":
        raise ValueError("Scene-aware slideshow requires visual_plan image mode SCENE.")

    script = load_timeline_script(Path(timeline_json))
    entries = parse_srt(Path(subtitle))
    pairs = match_script_to_srt(script, entries)
    entry_by_index = {index: entry for index, (_, entry) in enumerate(pairs)} if len(pairs) == len(script) else {}
    if not entry_by_index:
        # Preserve the source indices even when matching skipped unrelated SRT rows.
        for index, item in enumerate(script):
            for paired_item, entry in pairs:
                if paired_item is item:
                    entry_by_index[index] = entry
                    break
    required_matches = max(1, (len(script) + 1) // 2)
    if len(entry_by_index) < required_matches:
        raise ValueError(
            "Timeline JSON and subtitles appear to describe different scripts: "
            f"matched only {len(entry_by_index)}/{len(script)} timeline item(s)."
        )

    segments: list[ZoneSegment] = []
    expected_ordinal = 1
    previous_end = 0.0
    for asset in _scene_assets(plan):
        basename = _asset_basename(asset)
        match = SCENE_IMAGE_PATTERN.fullmatch(basename)
        if not match or int(match.group(1)) != expected_ordinal:
            raise ValueError(f"SCENE assets must be contiguous scene_0001..N; found {basename!r}.")
        start = asset.get("script_item_start", asset.get("item_start", asset.get("start_item_index")))
        end = asset.get("script_item_end", asset.get("item_end", asset.get("end_item_index")))
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end >= len(script):
            raise ValueError(f"Invalid script span for {basename}: {start!r}..{end!r}.")
        if start not in entry_by_index or end not in entry_by_index:
            raise ValueError(f"Could not map the complete script span for {basename} to subtitles.")
        image = Path(scenes_dir) / basename
        if not image.is_file():
            raise FileNotFoundError(f"Scene image not found: {image}")
        segment_start = entry_by_index[start].start
        segment_end = entry_by_index[end].end
        if segment_start < previous_end:
            raise ValueError(f"Overlapping or out-of-order scene span at {basename}.")
        if segment_start > previous_end and segments:
            segments[-1] = ZoneSegment(
                zone=segments[-1].zone,
                image=segments[-1].image,
                start=segments[-1].start,
                end=segment_start,
            )
        zone = str(asset.get("zone") or script[start].get("zone") or "SCENE")
        segments.append(ZoneSegment(zone=zone, image=image, start=segment_start, end=segment_end))
        previous_end = segment_end
        expected_ordinal += 1
    if segments:
        first = segments[0]
        segments[0] = ZoneSegment(zone=first.zone, image=first.image, start=0.0, end=first.end)
    return segments


def resolve_slideshow_timeline_mode(requested: str, visual_plan_json: Path | None) -> str:
    mode = str(requested or "auto").lower()
    if mode not in {"auto", "fixed", "zone", "scene"}:
        raise ValueError("slideshow_timeline_mode must be auto, fixed, zone, or scene.")
    if mode != "auto":
        return mode
    if visual_plan_json is not None and Path(visual_plan_json).is_file():
        try:
            plan = json.loads(Path(visual_plan_json).read_text(encoding="utf-8"))
            if isinstance(plan, dict) and _resolved_mode(plan) == "SCENE":
                return "scene"
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    # Without an authoritative SCENE plan, preserve the historical regular
    # slideshow behavior.  The legacy zone-aware flag still resolves to zone.
    return "fixed"
