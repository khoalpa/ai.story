"""Deterministic Flow graph projection."""
from __future__ import annotations

from typing import Any, Mapping

from studio.video_prompt_adapters.base import (
    common_clip,
    declared_capability_warnings,
    object_value,
)


class FlowAdapter:
    target = "FLOW"
    contract_target = "FLOW"
    adapter_id = "ai-story.flow-graph"
    adapter_version = "2.0"

    def project_clip(self, clip: Mapping[str, Any]) -> dict[str, Any]:
        item = common_clip(clip)
        return {
            "node_id": item.pop("clip_id"),
            "node_type": "video_generation",
            "inputs": item,
        }

    def project_plan(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        clips = [clip for clip in plan.get("clips", []) if isinstance(clip, dict)]
        nodes = [self.project_clip(clip) for clip in clips]
        edges = []
        for previous, current in zip(clips, clips[1:]):
            variants = object_value(current.get("generation_variants"))
            if variants.get("requested_continuity_mode") == "CHAINED_LAST_FRAME":
                edges.append({
                    "from": previous.get("clip_id"),
                    "to": current.get("clip_id"),
                    "binding": "last_frame_to_first_frame",
                })
        return {"target": self.target, "project": plan.get("project"), "nodes": nodes, "edges": edges}

    def capability_warnings(self, plan: Mapping[str, Any]) -> list[str]:
        return declared_capability_warnings(plan)


ADAPTER = FlowAdapter()

__all__ = ["ADAPTER", "FlowAdapter"]
