"""Disposable deterministic Veo/Flow projections from canonical video prompts."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any, Mapping

from studio.prompt_contract import PromptContract, load_prompt_contract

ADAPTERS = {
    "VEO": ("ai-story.veo-json", "1.0"),
    "FLOW": ("ai-story.flow-json", "1.0"),
}


def canonical_json_bytes(value: Any) -> bytes:
    text = unicodedata.normalize("NFC", json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return text.encode("utf-8")


def project_video_prompts(plan: Mapping[str, Any], target: str, *, source_bytes: bytes | None = None,
                          contract: PromptContract | None = None) -> tuple[str, bytes]:
    """Return the conventional filename and a reproducible, non-authoritative projection."""
    contract = contract or load_prompt_contract()
    target = target.upper()
    if target not in ADAPTERS or target not in contract.video_prompt_derivative_targets:
        raise ValueError(f"Chưa có adapter deterministic cho target {target!r}")
    adapter_id, adapter_version = ADAPTERS[target]
    canonical = source_bytes if source_bytes is not None else canonical_json_bytes(plan)
    if source_bytes is not None:
        try:
            decoded = json.loads(source_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Canonical source bytes không phải JSON UTF-8 hợp lệ") from exc
        if decoded != plan:
            raise ValueError("Canonical source bytes không tương đương plan đang projection")
    clips = []
    for clip in plan.get("clips", []):
        item = {
            "clip_id": clip.get("clip_id"),
            "duration_seconds": clip.get("duration_seconds"),
            "aspect_ratio": clip.get("aspect_ratio"),
            "prompt": clip.get("prompt"),
            "audio_prompt": clip.get("audio_prompt"),
            "negative_prompt": clip.get("avoid"),
            "reference_inputs": clip.get("reference_inputs"),
            "generation_variants": clip.get("generation_variants"),
            "continuity_in": clip.get("continuity_in"),
            "continuity_out": clip.get("continuity_out"),
            "transition_type": clip.get("transition_type"),
        }
        if target == "FLOW":
            item = {"node_id": item.pop("clip_id"), "node_type": "video_generation", **item}
        clips.append(item)
    target_payload = {
        "target": target,
        "project": plan.get("project"),
        "global_continuity_lock": plan.get("global_continuity_lock"),
        "clips" if target == "VEO" else "nodes": clips,
    }
    # Preserve the complete provider-neutral semantics. Target jobs are a view,
    # never a replacement source and therefore introduce no silent loss.
    payload = {"canonical_semantics": plan, "target_payload": target_payload}
    payload_bytes = canonical_json_bytes(payload)
    binding = {
        "source_file": contract.video_prompt_file_name,
        "source_schema_version": contract.video_prompt_schema_version,
        "source_digest_sha256": hashlib.sha256(canonical).hexdigest(),
        "target": target,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "projection_digest_sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }
    derived = {"projection_binding": binding, "projection_losses": [], "projection": payload}
    stem = contract.video_prompt_file_name.rsplit(".", 1)[0]
    return f"{stem}.{target.lower()}.json", canonical_json_bytes(derived)


def validate_projection(document: Mapping[str, Any], plan: Mapping[str, Any], *,
                        source_bytes: bytes | None = None, contract: PromptContract | None = None) -> bool:
    contract = contract or load_prompt_contract()
    binding = document.get("projection_binding")
    payload = document.get("projection")
    if not isinstance(binding, dict) or not isinstance(payload, dict):
        return False
    source = source_bytes if source_bytes is not None else canonical_json_bytes(plan)
    target = binding.get("target")
    return (target in ADAPTERS
            and document.get("projection_losses") == []
            and payload.get("canonical_semantics") == plan
            and binding.get("source_file") == contract.video_prompt_file_name
            and binding.get("source_schema_version") == contract.video_prompt_schema_version
            and binding.get("source_digest_sha256") == hashlib.sha256(source).hexdigest()
            and binding.get("adapter_id") == ADAPTERS[target][0]
            and binding.get("adapter_version") == ADAPTERS[target][1]
            and binding.get("projection_digest_sha256") == hashlib.sha256(canonical_json_bytes(payload)).hexdigest())


__all__ = ["canonical_json_bytes", "project_video_prompts", "validate_projection"]
