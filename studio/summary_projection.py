"""Deterministic projections from canonical summary.json into story workflows."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from studio.image_prompt_validation import validate_image_prompt_plan
from studio.story_schema import ZONES, validate_story_document
from studio.summary_schema import validate_summary_document
from studio.summary_visual_schema import validate_summary_visual_plan
from studio.video_prompt_v4 import validate_v5_plan
from studio.workflow_package import validate_visual_plan


def _require_summary(summary: Mapping[str, Any]) -> None:
    errors = validate_summary_document(summary)
    if errors:
        raise ValueError("summary.json không hợp lệ: " + "; ".join(errors))


def _split_into_eight(text: str) -> list[str]:
    words = text.split()
    if len(words) < len(ZONES):
        raise ValueError(
            "Narration cần ít nhất 8 từ để projection vào tám zone canonical"
        )
    chunks: list[str] = []
    for index in range(len(ZONES)):
        start = round(index * len(words) / len(ZONES))
        end = round((index + 1) * len(words) / len(ZONES))
        chunks.append(" ".join(words[start:end]))
    return chunks


def project_summary_to_story(summary: Mapping[str, Any]) -> dict[str, Any]:
    _require_summary(summary)
    meta = summary["meta"]
    narration_text = " ".join(str(row["text"]).strip() for row in summary["narration"])
    chunks = _split_into_eight(narration_text)
    target_minutes = meta.get("target_minutes") or max(
        0.1, len(narration_text.split()) / 150
    )
    story: dict[str, Any] = {
        "schema_version": "4.1.3",
        "meta": {
            "title": str(meta["title"]),
            "series": None,
            "episode": 1,
            "author": "Summary Adapter",
            "channel": "AI Story Studio",
            "profile": "ADULT_STANDARD",
            "age_band": "18+",
            "language": str(meta["language"]),
            "genre": str(meta["source_genre"]),
            "tone": str(meta["style"]),
            "target_minutes": float(target_minutes),
            "estimated_minutes": round(len(narration_text.split()) / 150, 2) or 0.01,
            "timing_method": "WHITESPACE_RATE_V1",
            "tags": ["summary"],
        },
        "characters": [
            {
                "character_id": "c001",
                "name": "Người dẫn chuyện",
                "age": None,
                "role": "Người dẫn chuyện kỹ thuật",
                "appearance": "Không xuất hiện bắt buộc trong hình",
                "personality": "Trung tính, chính xác",
                "voice_note": "Giọng đọc rõ ràng, điềm tĩnh",
            }
        ],
        "outline": [],
        "script": [],
    }
    for index, (zone, chunk) in enumerate(zip(ZONES, chunks), 1):
        scene_id = f"sc{index:03d}"
        story["outline"].append(
            {
                "scene_id": scene_id,
                "summary": chunk,
                "change": f"Hoàn thành phần {index} của bản tóm tắt",
                "setup_or_payoff": None,
            }
        )
        story["script"].append(
            {
                "id": f"s{index:04d}",
                "zone": zone,
                "scene_id": scene_id,
                "speaker": "narrator",
                "text": chunk,
                "emotion": "trung tính",
                "speed": 1.0,
                "pause_ms": 250,
                "ambience": None,
            }
        )
    errors = validate_story_document(story)
    if errors:
        raise ValueError("Projection story.json không hợp lệ: " + "; ".join(errors))
    return story


def project_summary_to_visual_plan(
    summary: Mapping[str, Any],
    story: Mapping[str, Any],
    summary_visual_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _require_summary(summary)
    story_errors = validate_story_document(story)
    if story_errors:
        raise ValueError("story.json không hợp lệ: " + "; ".join(story_errors))
    script = story["script"]
    visual_scenes: list[Mapping[str, Any]] = []
    if summary_visual_plan is not None:
        visual_errors = validate_summary_visual_plan(summary_visual_plan, summary)
        if visual_errors:
            raise ValueError(
                "summary_visual_plan không hợp lệ: " + "; ".join(visual_errors)
            )
        visual_scenes = list(summary_visual_plan["scenes"])
    assets: list[dict[str, Any]] = []

    def asset(
        basename: str, role: str, source_ids: list[str], brief: str
    ) -> dict[str, Any]:
        return {
            "basename": basename,
            "role": role,
            "source_script_ids": source_ids,
            "character_ids": [],
            "brief": brief,
            "landscape_prompt": f"Documentary illustration, landscape 16:9, {brief}, no text",
            "portrait_prompt": f"Documentary illustration, portrait 9:16, {brief}, no text",
        }

    assets.append(
        asset("cover.png", "COVER", ["s0001"], f"Bìa cho {summary['meta']['title']}")
    )
    assets.append(asset("greeting.png", "GREETING", ["s0001"], str(script[0]["text"])))
    for index, row in enumerate(script, 1):
        source = (
            visual_scenes[
                min(
                    (index - 1) * len(visual_scenes) // len(script),
                    len(visual_scenes) - 1,
                )
            ]
            if visual_scenes
            else None
        )
        projected = asset(
            f"scene_{index:04d}.png",
            "SCENE",
            [row["id"]],
            str(source["brief"]) if source is not None else str(row["text"]),
        )
        if source is not None:
            projected["landscape_prompt"] = source["landscape_prompt"]
            projected["portrait_prompt"] = source["portrait_prompt"]
        assets.append(projected)
    assets.append(
        asset("farewell.png", "FAREWELL", [script[-1]["id"]], str(script[-1]["text"]))
    )
    assets.append(
        asset("outro.png", "OUTRO", [script[-1]["id"]], "Khung kết thúc tối giản")
    )
    plan = {
        "schema_version": "4.1.3",
        "image_mode": "SCENE",
        "reference_mode": "DESCRIPTION_ONLY",
        "targets": {
            "landscape": {
                "size_policy": "MODEL_DEFAULT",
                "preferred_aspect_ratio": "16:9",
                "width": None,
                "height": None,
            },
            "portrait": {
                "size_policy": "MODEL_DEFAULT",
                "preferred_aspect_ratio": "9:16",
                "width": None,
                "height": None,
            },
        },
        "characters": [],
        "assets": assets,
    }
    errors = validate_visual_plan(plan)
    if errors:
        raise ValueError(
            "Projection visual_plan.json không hợp lệ: " + "; ".join(errors)
        )
    return plan


def project_summary_to_image_prompts(
    summary: Mapping[str, Any], story: Mapping[str, Any], visual_plan: Mapping[str, Any]
) -> dict[str, Any]:
    _require_summary(summary)
    story_raw = json.dumps(
        story, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    assets = []
    for index, row in enumerate(visual_plan["assets"], 1):
        assets.append(
            {
                "asset_id": f"asset_{index:04d}",
                "basename": row["basename"],
                "role": row["role"],
                "source_script_ids": list(row["source_script_ids"]),
                "character_ids": [],
                "brief": row["brief"],
                "landscape_prompt": row["landscape_prompt"],
                "portrait_prompt": row["portrait_prompt"],
                "must_show": [],
                "must_avoid": ["text", "watermark"],
            }
        )
    plan = {
        "image_prompt_version": "1.1",
        "prompt_version": "5.2.2",
        "source_story": {
            "schema_version": "4.1.3",
            "sha256": hashlib.sha256(story_raw).hexdigest(),
        },
        "image_mode": "SCENE",
        "prompt_encoding": {
            "standard": "T5-512",
            "tokenizer_id": "google/t5-v1_1-xxl",
            "max_tokens": 512,
            "count_scope": "RESOLVED_IMAGE_PROMPT",
            "overflow_policy": "REWRITE",
        },
        "style_lock": "Documentary illustration, accurate, consistent palette, no invented data.",
        "characters_prompt": "Người dẫn chuyện không cần xuất hiện trong hình.",
        "character_locks": [],
        "assets": assets,
        "limitations": [],
    }
    errors = validate_image_prompt_plan(
        plan, story, story_raw, expected_prompt_version="5.2.2"
    )
    if errors:
        raise ValueError(
            "Projection image_prompts.json không hợp lệ: " + "; ".join(errors)
        )
    return plan


def project_summary_to_video_prompts(
    summary: Mapping[str, Any], story: Mapping[str, Any]
) -> dict[str, Any]:
    _require_summary(summary)
    clips = []
    for index, row in enumerate(story["script"], 1):
        text = str(row["text"])
        clips.append(
            {
                "clip_id": f"clip_{index:04d}",
                "source_spans": [
                    {"script_id": row["id"], "start_char": 0, "end_char": len(text)}
                ],
                "estimated_seconds": round(max(0.1, len(text.split()) / 150 * 60), 2),
                "aspect_ratio": "16:9",
                "reference_paths": [],
                "prompt": f"Documentary scene illustrating: {text}",
                "narration": text,
                "audio_note": "Narration from exact story span",
                "transition": "CUT",
            }
        )
    plan = {
        "schema_version": "4.1.3",
        "source_mode": "STORY_ONLY",
        "target_model": None,
        "coverage": "FULL_STORY",
        "timing_basis": "ESTIMATED",
        "timing_config": {
            "method_id": "WHITESPACE_RATE_V1",
            "rate_per_minute": 150,
            "evidence_locator": None,
        },
        "clips": clips,
        "limitations": [],
    }
    story_raw = json.dumps(story, ensure_ascii=False).encode()
    result = validate_v5_plan(plan, members={"story.json": story_raw})
    if result["errors"]:
        raise ValueError(
            "Projection video_prompts.json không hợp lệ: " + "; ".join(result["errors"])
        )
    return plan


__all__ = [
    "project_summary_to_image_prompts",
    "project_summary_to_story",
    "project_summary_to_video_prompts",
    "project_summary_to_visual_plan",
]
