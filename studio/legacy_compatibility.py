"""Bounded legacy overlay router. It classifies; it never silently upgrades evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.workflow_package import read_archive, read_json

LEGACY_ADAPTER_ID = "LEGACY_PROGRESSIVE_PACKAGE_ADAPTER_01"
LEGACY_NAMES = {"stage1_checkpoint.zip": "STAGE1", "stage2_checkpoint.zip": "STAGE2"}
LEGACY_STORY_VERSIONS = {"1.0-IMPLICIT", "2.0", "2.1", "2.2"}


def inspect_legacy_package(path: Path, *, contract: PromptContract | None = None) -> dict[str, Any]:
    contract = contract or load_prompt_contract()
    errors: list[str] = []
    stage = LEGACY_NAMES.get(path.name.casefold())
    if stage is None:
        return {"status": "MIGRATION_REQUIRED", "errors": ["Basename không thuộc legacy allowlist."], "adapter_id": None}
    try:
        members = read_archive(path)
        if "workflow_manifest.json" in members:
            errors.append("Package có manifest phải đi CURRENT route, không được activate legacy overlay.")
        story = read_json(members["story.json"])
    except (OSError, KeyError, ValueError, UnicodeError) as exc:
        return {"status": "FAIL", "errors": [str(exc)], "adapter_id": LEGACY_ADAPTER_ID}
    schema = story.get("schema_version", "1.0-IMPLICIT")
    if schema not in LEGACY_STORY_VERSIONS:
        errors.append(f"Story schema {schema!r} không thuộc legacy allowlist.")
    if stage == "STAGE2":
        characters = story.get("characters")
        count = len(characters) if isinstance(characters, list) else -1
        expected_count = 13 + count
        if count < 0 or len(members) != expected_count:
            errors.append(f"Stage 2 legacy file_count={len(members)}; yêu cầu {expected_count}.")
    evidence = {
        "artifact_path": str(path), "detected_schema": "story", "detected_version": schema,
        "adapter_id": LEGACY_ADAPTER_ID,
    }
    # Exact original-version gates/fixtures are intentionally required before migration.
    status = "FAIL" if errors else "MIGRATION_REQUIRED"
    if not errors:
        errors.append("Đã phân loại đúng adapter nhưng chưa có matching legacy conformance fixture; không materialize CURRENT package.")
    return {"status": status, "stage": stage, "errors": errors, "adapter_id": LEGACY_ADAPTER_ID,
            "evidence": evidence, "members": members}


__all__ = ["inspect_legacy_package"]
