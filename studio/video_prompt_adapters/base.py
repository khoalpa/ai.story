"""Shared contracts and helpers for target-specific video prompt adapters."""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class VideoPromptAdapter(Protocol):
    adapter_id: str
    adapter_version: str
    contract_target: str
    target: str

    def project_clip(self, clip: Mapping[str, Any]) -> dict[str, Any]: ...

    def project_plan(self, plan: Mapping[str, Any]) -> dict[str, Any]: ...

    def capability_warnings(self, plan: Mapping[str, Any]) -> list[str]: ...


def object_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def reference_files(clip: Mapping[str, Any]) -> list[str]:
    refs = object_value(clip.get("reference_inputs"))
    values = [refs.get("zone_reference_frame"), refs.get("primary_frame"), refs.get("target_last_frame")]
    values.extend(string_list(refs.get("character_images")))
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in result:
            result.append(value)
    return result


def common_clip(clip: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "clip_id": clip.get("clip_id"),
        "sequence_index": clip.get("sequence_index"),
        "prompt": clip.get("prompt"),
        "negative_prompt": string_list(clip.get("avoid")),
        "audio_prompt": clip.get("audio_prompt"),
        "duration_seconds": clip.get("duration_seconds"),
        "aspect_ratio": clip.get("aspect_ratio"),
        "reference_images": reference_files(clip),
        "reference_inputs": clip.get("reference_inputs"),
        "generation_variants": clip.get("generation_variants"),
        "continuity_in": clip.get("continuity_in"),
        "continuity_out": clip.get("continuity_out"),
        "transition_type": clip.get("transition_type"),
    }


def declared_capability_warnings(plan: Mapping[str, Any]) -> list[str]:
    target = object_value(plan.get("generator_target"))
    capability = object_value(target.get("capability_profile"))
    warnings: list[str] = []
    for key in ("reference_images", "first_last_frame", "video_extension"):
        evidence = object_value(capability.get(key))
        if evidence.get("status") != "OBSERVED_SUPPORTED":
            warnings.append(f"capability_profile.{key} chưa được OBSERVED_SUPPORTED")
    return warnings


__all__ = [
    "VideoPromptAdapter",
    "common_clip",
    "declared_capability_warnings",
    "object_value",
    "reference_files",
    "string_list",
]
