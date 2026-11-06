"""Non-destructive migration helpers for canonical Summary documents."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from studio.summary_schema import validate_summary_document


def migrate_summary_v100_to_v110(document: Mapping[str, Any]) -> dict[str, Any]:
    """Project a v1.0 Summary document into v1.1 without mutating the source."""
    if document.get("schema_version") != "1.0.0":
        raise ValueError("Migration yêu cầu summary schema_version 1.0.0")
    migrated = deepcopy(dict(document))
    migrated["schema_version"] = "1.1.0"
    migrated["prompt_version"] = "1.4.0"
    meta = dict(migrated.get("meta") or {})
    meta.setdefault("citation_style", None)
    meta.setdefault("scene_density_seconds", None)
    meta.setdefault("max_scenes", None)
    migrated["meta"] = meta
    sources = []
    for row in migrated.get("sources") or []:
        source = dict(row)
        source.setdefault("authors", [])
        source.setdefault("published_at", None)
        source.setdefault("publisher", None)
        source.setdefault("url", None)
        source.setdefault("accessed_at", None)
        sources.append(source)
    migrated["sources"] = sources
    migrated.setdefault("claim_relations", [])
    migrated.setdefault("numeric_facts", [])
    migrated.setdefault("glossary", [])
    ordered = {
        key: migrated[key] for key in (
            "schema_version", "prompt_version", "meta", "sources", "locators", "sections",
            "claims", "claim_relations", "numeric_facts", "glossary", "narration", "limitations",
        )
    }
    errors = validate_summary_document(ordered)
    if errors:
        raise ValueError("Migration tạo kết quả không hợp lệ: " + "; ".join(errors))
    return ordered


def migrate_summary_document(document: Mapping[str, Any]) -> dict[str, Any]:
    version = document.get("schema_version")
    if version == "1.1.0":
        result = deepcopy(dict(document))
        errors = validate_summary_document(result)
        if errors:
            raise ValueError("Summary hiện hành không hợp lệ: " + "; ".join(errors))
        return result
    if version == "1.0.0":
        return migrate_summary_v100_to_v110(document)
    raise ValueError(f"Summary schema không được hỗ trợ: {version!r}")


__all__ = ["migrate_summary_document", "migrate_summary_v100_to_v110"]
