"""Deterministic Veo job projection."""
from __future__ import annotations

from typing import Any, Mapping

from studio.video_prompt_adapters.base import (
    common_clip,
    declared_capability_warnings,
    object_value,
)


class VeoAdapter:
    target = "VEO"
    contract_target = "VEO"
    adapter_id = "ai-story.veo-jobs"
    adapter_version = "2.0"

    def project_clip(self, clip: Mapping[str, Any]) -> dict[str, Any]:
        item = common_clip(clip)
        refs = object_value(clip.get("reference_inputs"))
        return {
            "clip_id": item["clip_id"],
            "model": None,
            "prompt": item["prompt"],
            "negative_prompt": item["negative_prompt"],
            "duration_seconds": item["duration_seconds"],
            "aspect_ratio": item["aspect_ratio"],
            "reference_images": item["reference_images"],
            "first_frame": refs.get("primary_frame"),
            "last_frame": refs.get("target_last_frame"),
            "audio_prompt": item["audio_prompt"],
            "generation_variants": item["generation_variants"],
            "continuity_in": item["continuity_in"],
            "continuity_out": item["continuity_out"],
            "transition_type": item["transition_type"],
        }

    def project_plan(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        target = object_value(plan.get("generator_target"))
        jobs = [self.project_clip(clip) for clip in plan.get("clips", []) if isinstance(clip, dict)]
        for job in jobs:
            job["model"] = target.get("preferred_model")
        return {"target": self.target, "project": plan.get("project"), "jobs": jobs}

    def capability_warnings(self, plan: Mapping[str, Any]) -> list[str]:
        return declared_capability_warnings(plan)


ADAPTER = VeoAdapter()

__all__ = ["ADAPTER", "VeoAdapter"]
