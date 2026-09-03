"""Deterministic, non-authoritative exports from canonical video prompts."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zipfile
from io import BytesIO
from typing import Any, Mapping

from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.video_prompt_adapters import adapter_targets, get_adapter
from studio.video_prompt_adapters.base import reference_files
from studio.video_voice import combined_prompt

ADAPTERS = {
    target: (get_adapter(target).adapter_id, get_adapter(target).adapter_version)
    for target in adapter_targets()
}


def canonical_json_bytes(value: Any) -> bytes:
    text = unicodedata.normalize("NFC", json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return text.encode("utf-8")


def _canonical_source(plan: Mapping[str, Any], source_bytes: bytes | None) -> bytes:
    canonical = source_bytes if source_bytes is not None else canonical_json_bytes(plan)
    if source_bytes is not None:
        try:
            decoded = json.loads(source_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Canonical source bytes không phải JSON UTF-8 hợp lệ") from exc
        if decoded != plan:
            raise ValueError("Canonical source bytes không tương đương plan đang projection")
    return canonical


def _adapter_for(target: str, contract: PromptContract):
    adapter = get_adapter(target)
    if adapter.contract_target not in contract.video_prompt_derivative_targets:
        raise ValueError(f"Prompt contract không cho phép adapter target {target!r}")
    return adapter


def project_video_prompts(plan: Mapping[str, Any], target: str, *, source_bytes: bytes | None = None,
                          contract: PromptContract | None = None) -> tuple[str, bytes]:
    """Return the legacy single-JSON projection with complete canonical semantics."""
    contract = contract or load_prompt_contract()
    adapter = _adapter_for(target, contract)
    canonical = _canonical_source(plan, source_bytes)
    target_payload = adapter.project_plan(plan)
    payload = {"canonical_semantics": plan, "target_payload": target_payload}
    payload_bytes = canonical_json_bytes(payload)
    binding = {
        "source_file": contract.video_prompt_file_name,
        "source_schema_version": contract.video_prompt_schema_version,
        "source_digest_sha256": hashlib.sha256(canonical).hexdigest(),
        "target": adapter.target,
        "adapter_id": adapter.adapter_id,
        "adapter_version": adapter.adapter_version,
        "projection_digest_sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }
    derived = {
        "projection_binding": binding,
        "projection_losses": [],
        "capability_warnings": adapter.capability_warnings(plan),
        "projection": payload,
    }
    stem = contract.video_prompt_file_name.rsplit(".", 1)[0]
    return f"{stem}.{adapter.target.lower()}.json", canonical_json_bytes(derived)


def prompt_text(plan: Mapping[str, Any], target: str, *, contract: PromptContract | None = None) -> bytes:
    """Build a portable copy/paste view without dropping identifiers or references."""
    adapter = _adapter_for(target, contract or load_prompt_contract())
    sections = []
    for clip in plan.get("clips", []):
        if not isinstance(clip, dict):
            continue
        projected = adapter.project_clip(clip)
        prompt = combined_prompt(clip)
        avoid = ", ".join(str(value) for value in clip.get("avoid", []) if isinstance(value, str))
        references = ", ".join(reference_files(clip)) or "—"
        sections.append(
            f"[{clip.get('clip_id', 'unknown')}] {adapter.target}\n"
            f"Duration: {clip.get('duration_seconds')}s | Aspect ratio: {clip.get('aspect_ratio')}\n"
            f"Prompt:\n{prompt}\nAvoid: {avoid or '—'}\nReferences: {references}\n"
            f"Target job: {canonical_json_bytes(projected).decode('utf-8')}"
        )
    return unicodedata.normalize("NFC", "\n\n".join(sections) + ("\n" if sections else "")).encode("utf-8")


def _zip_entry(name: str, raw: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info, raw


def build_prompt_package(plan: Mapping[str, Any], target: str, *, source_bytes: bytes | None = None,
                         contract: PromptContract | None = None) -> tuple[str, bytes]:
    """Build a reproducible ZIP containing per-clip jobs, text, bindings and order."""
    contract = contract or load_prompt_contract()
    adapter = _adapter_for(target, contract)
    canonical = _canonical_source(plan, source_bytes)
    target_payload = adapter.project_plan(plan)
    clips = [clip for clip in plan.get("clips", []) if isinstance(clip, dict)]
    files: dict[str, bytes] = {
        f"canonical/{contract.video_prompt_file_name}": canonical,
        "target_payload.json": canonical_json_bytes(target_payload),
        "prompts.txt": prompt_text(plan, adapter.target, contract=contract),
        "references.json": canonical_json_bytes({str(clip.get("clip_id")): reference_files(clip) for clip in clips}),
        "generation-order.json": canonical_json_bytes({
            "clip_ids": [clip.get("clip_id") for clip in clips],
            "strategy": "dependency_order",
        }),
        "README.txt": ("Native voice prompts for manual copy/paste into the selected web video generator.\n"
                       "Each prompts/*.txt file is self-contained. Choose a model with native audio support.\n").encode("utf-8"),
    }
    for index, clip in enumerate(clips, 1):
        clip_id = str(clip.get("clip_id", f"clip_{index:04d}"))
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", clip_id)
        files[f"prompts/{safe_id}.json"] = canonical_json_bytes(adapter.project_clip(clip))
        files[f"prompts/{safe_id}.txt"] = (combined_prompt(clip) + "\n").encode("utf-8")
    rows = [
        {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
        for name, raw in sorted(files.items())
    ]
    manifest = {
        "schema_version": "1.0",
        "source_file": contract.video_prompt_file_name,
        "source_schema_version": contract.video_prompt_schema_version,
        "source_digest_sha256": hashlib.sha256(canonical).hexdigest(),
        "target": adapter.target,
        "adapter_id": adapter.adapter_id,
        "adapter_version": adapter.adapter_version,
        "capability_warnings": adapter.capability_warnings(plan),
        "semantic_losses": [],
        "files": rows,
    }
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info, manifest_raw = _zip_entry("manifest.json", canonical_json_bytes(manifest))
        archive.writestr(info, manifest_raw)
        for name, raw in sorted(files.items()):
            info, entry_raw = _zip_entry(name, raw)
            archive.writestr(info, entry_raw)
    stem = contract.video_prompt_file_name.rsplit(".", 1)[0]
    return f"{stem}.{adapter.target.lower()}.zip", buffer.getvalue()


def validate_projection(document: Mapping[str, Any], plan: Mapping[str, Any], *,
                        source_bytes: bytes | None = None, contract: PromptContract | None = None) -> bool:
    contract = contract or load_prompt_contract()
    binding = document.get("projection_binding")
    payload = document.get("projection")
    if not isinstance(binding, dict) or not isinstance(payload, dict):
        return False
    source = source_bytes if source_bytes is not None else canonical_json_bytes(plan)
    try:
        adapter = _adapter_for(str(binding.get("target", "")), contract)
    except ValueError:
        return False
    return (
        document.get("projection_losses") == []
        and payload.get("canonical_semantics") == plan
        and binding.get("source_file") == contract.video_prompt_file_name
        and binding.get("source_schema_version") == contract.video_prompt_schema_version
        and binding.get("source_digest_sha256") == hashlib.sha256(source).hexdigest()
        and binding.get("adapter_id") == adapter.adapter_id
        and binding.get("adapter_version") == adapter.adapter_version
        and binding.get("projection_digest_sha256") == hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    )


__all__ = [
    "ADAPTERS",
    "build_prompt_package",
    "canonical_json_bytes",
    "project_video_prompts",
    "prompt_text",
    "validate_projection",
]
