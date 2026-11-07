"""Non-destructive migration helpers for canonical Summary documents."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from studio.summary_schema import validate_summary_document

VALID_CITATION_STYLES = {"MARKDOWN", "APA", "MLA", "CHICAGO", "BIBTEX"}


def _id_mapping(rows: Any, field: str, prefix: str, digits: int) -> dict[str, str]:
    if not isinstance(rows, list):
        raise ValueError(f"{field} collection phải là array")
    mapping: dict[str, str] = {}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, Mapping) or not isinstance(row.get(field), str):
            raise ValueError(f"{field} tại vị trí {index} không hợp lệ")
        old = str(row[field])
        if old in mapping:
            raise ValueError(f"Không thể chuẩn hóa {field} bị trùng: {old}")
        mapping[old] = f"{prefix}_{index:0{digits}d}"
    return mapping


def _references(values: Any, mapping: Mapping[str, str], label: str) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"{label} phải là array")
    missing = [str(value) for value in values if value not in mapping]
    if missing:
        raise ValueError(f"{label} tham chiếu ID không tồn tại: {', '.join(missing)}")
    return [mapping[str(value)] for value in values]


def normalize_summary_v110_ids(
    document: Mapping[str, Any], *, citation_style: str = "MARKDOWN"
) -> dict[str, Any]:
    """Normalize a legacy-shaped v1.1 document to the runtime ID contract."""
    if document.get("schema_version") != "1.1.0":
        raise ValueError("Chuẩn hóa yêu cầu summary schema_version 1.1.0")
    if citation_style not in VALID_CITATION_STYLES:
        raise ValueError(f"citation_style không hỗ trợ: {citation_style}")
    migrated = deepcopy(dict(document))
    source_map = _id_mapping(migrated.get("sources"), "source_id", "src", 3)
    locator_map = _id_mapping(migrated.get("locators"), "locator_id", "loc", 4)
    section_map = _id_mapping(migrated.get("sections"), "section_id", "section", 3)
    claim_map = _id_mapping(migrated.get("claims"), "claim_id", "claim", 4)
    numeric_map = _id_mapping(migrated.get("numeric_facts"), "numeric_fact_id", "num", 4)
    narration_map = _id_mapping(migrated.get("narration"), "narration_id", "narration", 4)

    meta = dict(migrated.get("meta") or {})
    if meta.get("citation_style") not in VALID_CITATION_STYLES | {None}:
        meta["citation_style"] = citation_style
    migrated["meta"] = meta
    for row in migrated["sources"]:
        row["source_id"] = source_map[row["source_id"]]
    for row in migrated["locators"]:
        row["locator_id"] = locator_map[row["locator_id"]]
        row["source_id"] = source_map.get(row["source_id"], row["source_id"])
    for row in migrated["sections"]:
        row["section_id"] = section_map[row["section_id"]]
        row["source_id"] = source_map.get(row["source_id"], row["source_id"])
        row["locator_ids"] = _references(row.get("locator_ids"), locator_map, "sections.locator_ids")
    for row in migrated["claims"]:
        row["claim_id"] = claim_map[row["claim_id"]]
        row["source_ids"] = _references(row.get("source_ids"), source_map, "claims.source_ids")
        row["locator_ids"] = _references(row.get("locator_ids"), locator_map, "claims.locator_ids")
    for row in migrated.get("claim_relations", []):
        row["from_claim_id"] = claim_map.get(row.get("from_claim_id"), row.get("from_claim_id"))
        row["to_claim_id"] = claim_map.get(row.get("to_claim_id"), row.get("to_claim_id"))
    for row in migrated["numeric_facts"]:
        row["numeric_fact_id"] = numeric_map[row["numeric_fact_id"]]
        row["locator_ids"] = _references(row.get("locator_ids"), locator_map, "numeric_facts.locator_ids")
    for row in migrated.get("glossary", []):
        row["locator_ids"] = _references(row.get("locator_ids"), locator_map, "glossary.locator_ids")
    for row in migrated["narration"]:
        row["narration_id"] = narration_map[row["narration_id"]]
        section_id = row.get("section_id")
        if section_id not in section_map:
            raise ValueError(f"narration.section_id tham chiếu ID không tồn tại: {section_id}")
        row["section_id"] = section_map[str(section_id)]
        row["claim_ids"] = _references(row.get("claim_ids"), claim_map, "narration.claim_ids")
    errors = validate_summary_document(migrated)
    if errors:
        raise ValueError("Chuẩn hóa tạo kết quả không hợp lệ: " + "; ".join(errors))
    return migrated


def migrate_summary_v100_to_v110(document: Mapping[str, Any]) -> dict[str, Any]:
    """Project a v1.0 Summary document into v1.1 without mutating the source."""
    if document.get("schema_version") != "1.0.0":
        raise ValueError("Migration yêu cầu summary schema_version 1.0.0")
    migrated = deepcopy(dict(document))
    migrated["schema_version"] = "1.1.0"
    migrated["prompt_version"] = "1.5.0"
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


__all__ = [
    "migrate_summary_document",
    "migrate_summary_v100_to_v110",
    "normalize_summary_v110_ids",
]
