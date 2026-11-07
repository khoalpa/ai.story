"""Closed-schema validation for summary_visual_plan.json."""

from __future__ import annotations

from typing import Any, Mapping

ROOT_FIELDS = {
    "schema_version",
    "prompt_version",
    "image_mode",
    "coverage",
    "reference_mode",
    "targets",
    "style_lock",
    "scenes",
}
TARGET_FIELDS = {"size_policy", "preferred_aspect_ratio", "width", "height"}
SCENE_FIELDS = {
    "scene_id",
    "source_locator_ids",
    "narration_ids",
    "role",
    "visual_type",
    "visual_fact",
    "brief",
    "numeric_fact_ids",
    "on_screen_text",
    "landscape_prompt",
    "portrait_prompt",
    "limitations",
}
ROLES = {
    "COVER",
    "INTRO",
    "CONCEPT",
    "EVENT",
    "PROCESS",
    "EVIDENCE",
    "COMPARISON",
    "TRANSITION",
    "CONCLUSION",
    "OUTRO",
}
VISUAL_TYPES = {
    "ILLUSTRATION",
    "RECONSTRUCTION",
    "DIAGRAM",
    "TIMELINE",
    "MAP",
    "DATA_CHART",
    "QUOTE_CARD",
    "TITLE_CARD",
}


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strings(value: object, *, empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (empty or bool(value))
        and all(_text(item) for item in value)
        and len(value) == len(set(value))
    )


def validate_summary_visual_plan(plan: Any, summary: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, Mapping):
        return ["summary_visual_plan root phải là object"]
    if (
        set(plan) != ROOT_FIELDS
        or plan.get("schema_version") != "1.0.0"
        or plan.get("prompt_version") != "1.5.0"
    ):
        errors.append("summary_visual_plan root/schema/prompt version không hợp lệ")
    if plan.get("image_mode") not in {"SCENE", "ZONE"} or plan.get("coverage") not in {
        "FULL_SUMMARY",
        "KEY_SCENES",
    }:
        errors.append("summary_visual_plan image_mode/coverage không hợp lệ")
    if plan.get("reference_mode") not in {
        "IMAGE_REFERENCE",
        "DESCRIPTION_ONLY",
    } or not _text(plan.get("style_lock")):
        errors.append("summary_visual_plan reference_mode/style_lock không hợp lệ")
    targets = plan.get("targets")
    if not isinstance(targets, Mapping) or set(targets) != {"landscape", "portrait"}:
        errors.append("summary_visual_plan.targets không hợp lệ")
    else:
        for orientation, ratio in (("landscape", "16:9"), ("portrait", "9:16")):
            target = targets.get(orientation)
            if not isinstance(target, Mapping) or set(target) != TARGET_FIELDS:
                errors.append(f"targets.{orientation} không đúng closed schema")
                continue
            policy = target.get("size_policy")
            if (
                policy not in {"MODEL_DEFAULT", "EXACT"}
                or target.get("preferred_aspect_ratio") != ratio
            ):
                errors.append(f"targets.{orientation} policy/ratio không hợp lệ")
            width, height = target.get("width"), target.get("height")
            if policy == "MODEL_DEFAULT" and (width is not None or height is not None):
                errors.append(
                    f"targets.{orientation} MODEL_DEFAULT yêu cầu width/height null"
                )
            if policy == "EXACT" and not (
                type(width) is int and width > 0 and type(height) is int and height > 0
            ):
                errors.append(f"targets.{orientation} EXACT thiếu kích thước")
    locator_ids = {
        row.get("locator_id")
        for row in summary.get("locators", [])
        if isinstance(row, Mapping)
    }
    narration_ids = {
        row.get("narration_id")
        for row in summary.get("narration", [])
        if isinstance(row, Mapping)
    }
    numeric_ids = {
        row.get("numeric_fact_id")
        for row in summary.get("numeric_facts", [])
        if isinstance(row, Mapping)
    }
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append("summary_visual_plan.scenes phải là array không rỗng")
        return errors
    for index, row in enumerate(scenes, 1):
        if not isinstance(row, Mapping) or set(row) != SCENE_FIELDS:
            errors.append(f"scenes[{index}] không đúng closed schema")
            continue
        if row.get("scene_id") != f"scene_{index:04d}":
            errors.append(f"scenes[{index}].scene_id không liên tục")
        if row.get("role") not in ROLES or row.get("visual_type") not in VISUAL_TYPES:
            errors.append(f"scenes[{index}] role/visual_type không hợp lệ")
        for field in ("visual_fact", "brief", "landscape_prompt", "portrait_prompt"):
            if not _text(row.get(field)):
                errors.append(f"scenes[{index}].{field} phải là string không rỗng")
        for field, allowed, allow_empty in (
            ("source_locator_ids", locator_ids, True),
            ("narration_ids", narration_ids, False),
            ("numeric_fact_ids", numeric_ids, True),
        ):
            if (
                not _strings(row.get(field), empty=allow_empty)
                or not set(row.get(field, [])) <= allowed
            ):
                errors.append(f"scenes[{index}].{field} không hợp lệ")
        if row.get("visual_type") == "DATA_CHART" and not row.get("numeric_fact_ids"):
            errors.append(f"scenes[{index}] DATA_CHART cần numeric_fact_ids")
        if not isinstance(row.get("on_screen_text"), str) or not _strings(
            row.get("limitations")
        ):
            errors.append(f"scenes[{index}] on_screen_text/limitations không hợp lệ")
    return errors


__all__ = ["ROLES", "VISUAL_TYPES", "validate_summary_visual_plan"]
