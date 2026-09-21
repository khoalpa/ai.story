"""Deterministic Gemini video-prompt projection."""
from __future__ import annotations

from typing import Any, Mapping

from studio.video_prompt_adapters.base import (
    common_clip,
    declared_capability_warnings,
    object_value,
)


class GeminiAdapter:
    target = "GEMINI"
    contract_target = "OTHER_EXPLICIT_ADAPTER"
    adapter_id = "ai-story.gemini-video-prompts"
    adapter_version = "1.0"

    def project_clip(self, clip: Mapping[str, Any]) -> dict[str, Any]:
        item = common_clip(clip)
        refs = object_value(clip.get("reference_inputs"))
        return {
            "clip_id": item["clip_id"],
            "prompt": item["copy_paste_prompt"],
            "negative_prompt": item["negative_prompt"],
            "duration_seconds": item["duration_seconds"],
            "aspect_ratio": item["aspect_ratio"],
            "reference_images": item["reference_images"],
            "previous_clip_id": refs.get("previous_clip_id"),
            "audio_prompt": item["audio_prompt"],
            "voice_plan": item["voice_plan"],
            "generation_variants": item["generation_variants"],
            "continuity_in": item["continuity_in"],
            "continuity_out": item["continuity_out"],
            "transition_type": item["transition_type"],
        }

    def project_plan(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        clips = [self.project_clip(clip) for clip in plan.get("clips", []) if isinstance(clip, dict)]
        return {
            "target": self.target,
            "project": plan.get("project"),
            "generation_order": [clip["clip_id"] for clip in clips],
            "clips": clips,
        }

    def capability_warnings(self, plan: Mapping[str, Any]) -> list[str]:
        return declared_capability_warnings(plan)


ADAPTER = GeminiAdapter()

__all__ = ["ADAPTER", "GeminiAdapter"]
