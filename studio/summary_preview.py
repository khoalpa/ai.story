"""Timing and cross-artifact preview for canonical Summary narration."""
from __future__ import annotations

from typing import Any, Mapping, TypedDict

from studio.summary_projection import (
    project_summary_to_story,
    project_summary_to_video_prompts,
    project_summary_to_visual_plan,
)
from studio.summary_schema import validate_summary_document


class SummaryTiming(TypedDict):
    word_count: int
    rate_per_minute: float
    estimated_minutes: float
    target_minutes: float | None
    delta_minutes: float | None
    delta_percent: float | None


def estimate_summary_timing(
    summary: Mapping[str, Any], *, rate_per_minute: float = 150,
) -> SummaryTiming:
    errors = validate_summary_document(summary)
    if errors:
        raise ValueError("summary.json không hợp lệ: " + "; ".join(errors))
    if rate_per_minute <= 0:
        raise ValueError("rate_per_minute phải > 0")
    word_count = sum(len(str(row["text"]).split()) for row in summary["narration"])
    estimated_minutes = word_count / rate_per_minute
    target = summary["meta"].get("target_minutes")
    delta = estimated_minutes - float(target) if target is not None else None
    percent = delta / float(target) * 100 if delta is not None and target not in {None, 0} else None
    return {
        "word_count": word_count,
        "rate_per_minute": rate_per_minute,
        "estimated_minutes": round(estimated_minutes, 2),
        "target_minutes": target,
        "delta_minutes": round(delta, 2) if delta is not None else None,
        "delta_percent": round(percent, 1) if percent is not None else None,
    }


def _narration_word_ranges(summary: Mapping[str, Any]) -> list[tuple[str, int, int]]:
    ranges, cursor = [], 0
    for row in summary["narration"]:
        count = len(str(row["text"]).split())
        ranges.append((str(row["narration_id"]), cursor, cursor + count))
        cursor += count
    return ranges


def preview_projection_mapping(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    story = project_summary_to_story(summary)
    visual = project_summary_to_visual_plan(summary, story)
    video = project_summary_to_video_prompts(summary, story)
    ranges = _narration_word_ranges(summary)
    rows: list[dict[str, Any]] = []
    cursor = 0
    scene_assets = [row for row in visual["assets"] if row["role"] == "SCENE"]
    for index, (script, scene, clip) in enumerate(zip(story["script"], scene_assets, video["clips"]), 1):
        word_count = len(str(script["text"]).split())
        start, end = cursor, cursor + word_count
        narration_ids = [identifier for identifier, source_start, source_end in ranges
                         if source_start < end and source_end > start]
        rows.append({
            "part": index,
            "narration_ids": narration_ids,
            "story_script_id": script["id"],
            "zone": script["zone"],
            "scene": scene["basename"],
            "video_clip": clip["clip_id"],
            "words": word_count,
            "estimated_seconds": clip["estimated_seconds"],
            "text": script["text"],
        })
        cursor = end
    return rows


__all__ = ["estimate_summary_timing", "preview_projection_mapping"]
