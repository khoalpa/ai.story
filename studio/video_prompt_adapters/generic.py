"""Portable human-readable and JSON prompt projection."""
from __future__ import annotations

from typing import Any, Mapping

from studio.video_prompt_adapters.base import common_clip


class GenericAdapter:
    target = "GENERIC"
    contract_target = "OTHER_EXPLICIT_ADAPTER"
    adapter_id = "ai-story.generic-video-prompts"
    adapter_version = "1.0"

    def project_clip(self, clip: Mapping[str, Any]) -> dict[str, Any]:
        return common_clip(clip)

    def project_plan(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        clips = [self.project_clip(clip) for clip in plan.get("clips", []) if isinstance(clip, dict)]
        return {"target": self.target, "project": plan.get("project"), "clips": clips}

    def capability_warnings(self, plan: Mapping[str, Any]) -> list[str]:
        return ["Generic export không cam kết schema hay capability của một provider cụ thể."]


ADAPTER = GenericAdapter()

__all__ = ["ADAPTER", "GenericAdapter"]
