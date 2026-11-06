"""Build and summarize canonical Summary visual plans."""

from __future__ import annotations

from typing import Any, Mapping

from studio.summary_schema import validate_summary_document
from studio.summary_visual_schema import validate_summary_visual_plan


def build_summary_visual_plan(summary: Mapping[str, Any]) -> dict[str, Any]:
    errors = validate_summary_document(summary)
    if errors:
        raise ValueError("summary.json không hợp lệ: " + "; ".join(errors))
    claims = {row["claim_id"]: row for row in summary["claims"]}
    scenes = []
    for index, narration in enumerate(summary["narration"], 1):
        linked_claims = [
            claims[identifier]
            for identifier in narration["claim_ids"]
            if identifier in claims
        ]
        locators = sorted(
            {locator for claim in linked_claims for locator in claim["locator_ids"]}
        )
        text = str(narration["text"])
        role = (
            "INTRO"
            if index == 1
            else "CONCLUSION"
            if index == len(summary["narration"])
            else "CONCEPT"
        )
        scenes.append(
            {
                "scene_id": f"scene_{index:04d}",
                "source_locator_ids": locators,
                "narration_ids": [narration["narration_id"]],
                "role": role,
                "visual_type": "ILLUSTRATION",
                "visual_fact": text,
                "brief": text,
                "numeric_fact_ids": [],
                "on_screen_text": "",
                "landscape_prompt": f"Documentary illustration, landscape 16:9, {text}, no text",
                "portrait_prompt": f"Documentary illustration, portrait 9:16, {text}, no text",
                "limitations": [],
            }
        )
    plan = {
        "schema_version": "1.0.0",
        "prompt_version": "1.4.0",
        "image_mode": summary["meta"]["image_mode"],
        "coverage": summary["meta"]["coverage"],
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
        "style_lock": "Documentary illustration, accurate source-grounded visuals, consistent palette.",
        "scenes": scenes,
    }
    errors = validate_summary_visual_plan(plan, summary)
    if errors:
        raise ValueError("summary_visual_plan không hợp lệ: " + "; ".join(errors))
    return plan


def visual_density(
    summary: Mapping[str, Any], plan: Mapping[str, Any], estimated_minutes: float
) -> dict[str, float | int | None]:
    count = len(plan.get("scenes", []))
    seconds = estimated_minutes * 60
    return {
        "scene_count": count,
        "seconds_per_scene": round(seconds / count, 2) if count else None,
        "target_density_seconds": summary["meta"].get("scene_density_seconds"),
        "max_scenes": summary["meta"].get("max_scenes"),
    }


__all__ = ["build_summary_visual_plan", "visual_density"]
