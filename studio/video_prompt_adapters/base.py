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
    # v1.1 exposes static character assets only. Previous generated output is
    # represented by the continuity ID/flags, never by a packaged file path.
    return list(dict.fromkeys(string_list(refs.get("character_images"))))


def common_clip(clip: Mapping[str, Any]) -> dict[str, Any]:
    from studio.video_voice import combined_prompt
    return {
        "clip_id": clip.get("clip_id"),
        "sequence_index": clip.get("sequence_index"),
        "prompt": combined_prompt(clip),
        "visual_prompt": clip.get("prompt"),
        "negative_prompt": string_list(clip.get("avoid")),
        "audio_prompt": clip.get("audio_prompt"),
        "voice_plan": clip.get("voice_plan"),
        "copy_paste_prompt": combined_prompt(clip),
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
    required_by_mode = {
        "IMAGE_TO_VIDEO": "reference_images",
        "REFERENCE_IMAGES": "reference_images",
        "FIRST_LAST_FRAME": "first_last_frame",
        "VIDEO_EXTENSION": "video_extension",
    }
    required = {
        required_by_mode[mode]
        for clip in plan.get("clips", []) if isinstance(clip, dict)
        for variants in [object_value(clip.get("generation_variants"))]
        for mode in [variants.get("preferred_mode")]
        if mode in required_by_mode
    }
    for key in sorted(required):
        evidence = object_value(capability.get(key))
        if not evidence.get("supported") or evidence.get("status") == "NOT_VERIFIED":
            warnings.append(f"capability_profile.{key} chưa tương thích với preferred_mode đang dùng")
        elif evidence.get("status") != "OBSERVED_SUPPORTED":
            warnings.append(f"capability_profile.{key} tương thích nhưng chưa được xác minh tại runtime")
    return warnings


__all__ = [
    "VideoPromptAdapter",
    "common_clip",
    "declared_capability_warnings",
    "object_value",
    "reference_files",
    "string_list",
]
