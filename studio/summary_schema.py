"""Closed-schema validation for canonical summary.json artifacts."""
from __future__ import annotations

import math
import re
from typing import Any, Mapping, TypeGuard

ROOT_FIELDS = {"schema_version", "prompt_version", "meta", "sources", "locators", "sections", "claims", "claim_relations", "numeric_facts", "glossary", "narration", "limitations"}
META_FIELDS = {"title", "output_type", "source_genre", "style", "audience", "language", "target_words", "target_minutes", "image_mode", "coverage", "citation_style", "scene_density_seconds", "max_scenes"}
SOURCE_FIELDS = {"source_id", "title", "type", "version", "authors", "published_at", "publisher", "url", "accessed_at", "mime_type", "size_bytes", "sha256", "extraction_method", "ocr_status", "scope_read"}
LOCATOR_FIELDS = {"locator_id", "source_id", "kind", "label", "page", "section", "start_char", "end_char", "timestamp_start_ms", "timestamp_end_ms"}
SECTION_FIELDS = {"section_id", "source_id", "locator_ids", "summary", "key_points", "uncertainties"}
CLAIM_FIELDS = {"claim_id", "statement", "claim_type", "source_ids", "locator_ids", "confidence", "included_in_summary"}
NARRATION_FIELDS = {"narration_id", "section_id", "text", "claim_ids"}
RELATION_FIELDS = {"from_claim_id", "type", "to_claim_id"}
NUMERIC_FACT_FIELDS = {"numeric_fact_id", "value", "unit", "population", "period", "locator_ids"}
GLOSSARY_FIELDS = {"term", "definition", "original_term", "do_not_translate", "locator_ids"}
OUTPUT_TYPES = {
    "SUMMARY", "ANALYSIS", "SUMMARY_ANALYSIS", "STUDY_GUIDE", "EXECUTIVE_BRIEF",
    "NARRATED_SCRIPT", "CHAPTER_BY_CHAPTER", "COMPARE_SOURCES", "ARGUMENT_MAP",
    "TIMELINE", "CONCEPT_MAP", "CHARACTER_MAP", "DATA_BRIEF", "ACTION_ITEMS",
    "TEACHING_SCRIPT", "FAQ", "QUESTION_ANSWER", "CUSTOM",
}
SOURCE_GENRES = {"FICTION", "NONFICTION", "ACADEMIC", "BUSINESS_REPORT", "LEGAL_POLICY", "TECHNICAL", "TRANSCRIPT", "MIXED"}
STYLES = {"NEUTRAL_CLEAR", "ACADEMIC", "POPULAR", "STORYTELLING", "CRITICAL", "EXECUTIVE", "DOCUMENTARY", "CUSTOM"}
LOCATOR_KINDS = {"PDF_PAGE", "EPUB_CFI", "DOCX_HEADING", "TEXT_OFFSET", "WEB_FRAGMENT", "TIMESTAMP", "TABLE_CELL", "FIGURE", "OTHER"}
CLAIM_TYPES = {"SOURCE", "INFERENCE", "EXTERNAL"}
CONFIDENCES = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
RELATION_TYPES = {"SUPPORTS", "CONTRADICTS", "QUALIFIES", "CAUSES", "CORRELATES_WITH", "EXEMPLIFIES", "DEPENDS_ON"}
DIGEST = re.compile(r"[0-9a-f]{64}")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object, *, allow_empty: bool = True) -> bool:
    return isinstance(value, list) and (allow_empty or bool(value)) and all(_text(item) for item in value) and len(value) == len(set(value))


def _id(value: object, prefix: str, digits: int = 3) -> TypeGuard[str]:
    return isinstance(value, str) and re.fullmatch(rf"{prefix}_[0-9]{{{digits}}}", value) is not None


def validate_summary_document(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, Mapping):
        return ["summary.json root phải là object"]
    if set(document) != ROOT_FIELDS:
        errors.append("summary.json root không đúng closed schema")
    if document.get("schema_version") != "1.1.0" or document.get("prompt_version") != "1.5.0":
        errors.append("summary schema/prompt version không hợp lệ")

    meta = document.get("meta")
    if not isinstance(meta, Mapping) or set(meta) != META_FIELDS:
        errors.append("summary.meta không đúng closed schema")
        meta = {}
    for field in ("title", "audience", "language"):
        if not _text(meta.get(field)):
            errors.append(f"meta.{field} phải là string không rỗng")
    for field, allowed in (("output_type", OUTPUT_TYPES), ("source_genre", SOURCE_GENRES), ("style", STYLES)):
        if meta.get(field) not in allowed:
            errors.append(f"meta.{field} không hợp lệ")
    if meta.get("image_mode") not in {"SCENE", "ZONE"} or meta.get("coverage") not in {"FULL_SUMMARY", "KEY_SCENES"}:
        errors.append("meta.image_mode/coverage không hợp lệ")
    for field in ("target_words", "target_minutes"):
        value = meta.get(field)
        if value is not None and (type(value) not in {int, float} or not math.isfinite(value) or value <= 0):
            errors.append(f"meta.{field} phải là number > 0 hoặc null")
    if meta.get("citation_style") not in {None, "MARKDOWN", "APA", "MLA", "CHICAGO", "BIBTEX"}:
        errors.append("meta.citation_style không hợp lệ")
    density, max_scenes = meta.get("scene_density_seconds"), meta.get("max_scenes")
    if density is not None and (type(density) not in {int, float} or not math.isfinite(density) or density <= 0):
        errors.append("meta.scene_density_seconds phải là number > 0 hoặc null")
    if max_scenes is not None and (type(max_scenes) is not int or max_scenes <= 0):
        errors.append("meta.max_scenes phải là integer > 0 hoặc null")

    sources = document.get("sources")
    source_ids: set[str] = set()
    if not isinstance(sources, list) or not sources:
        errors.append("sources phải là array không rỗng")
    else:
        for index, row in enumerate(sources, 1):
            if not isinstance(row, Mapping) or set(row) != SOURCE_FIELDS:
                errors.append(f"sources[{index}] không đúng closed schema")
                continue
            source_id = row.get("source_id")
            if not _id(source_id, "src") or source_id in source_ids:
                errors.append(f"sources[{index}].source_id không hợp lệ hoặc trùng")
            else:
                source_ids.add(source_id)
            if not _text(row.get("title")) or not _text(row.get("type")) or not _text(row.get("scope_read")):
                errors.append(f"sources[{index}] thiếu title/type/scope_read")
            if not _string_list(row.get("authors")):
                errors.append(f"sources[{index}].authors không hợp lệ")
            for field in ("version", "published_at", "publisher", "url", "accessed_at", "mime_type", "extraction_method", "ocr_status"):
                if row.get(field) is not None and not _text(row.get(field)):
                    errors.append(f"sources[{index}].{field} không hợp lệ")
            size, digest = row.get("size_bytes"), row.get("sha256")
            if size is not None and (type(size) is not int or size < 0):
                errors.append(f"sources[{index}].size_bytes không hợp lệ")
            if digest is not None and (not isinstance(digest, str) or DIGEST.fullmatch(digest) is None):
                errors.append(f"sources[{index}].sha256 không hợp lệ")

    locators = document.get("locators")
    locator_ids: set[str] = set()
    if not isinstance(locators, list):
        errors.append("locators phải là array")
    else:
        for index, row in enumerate(locators, 1):
            if not isinstance(row, Mapping) or set(row) != LOCATOR_FIELDS:
                errors.append(f"locators[{index}] không đúng closed schema")
                continue
            locator_id = row.get("locator_id")
            if not _id(locator_id, "loc", 4) or locator_id in locator_ids:
                errors.append(f"locators[{index}].locator_id không hợp lệ hoặc trùng")
            else:
                locator_ids.add(locator_id)
            if row.get("source_id") not in source_ids or row.get("kind") not in LOCATOR_KINDS or not _text(row.get("label")):
                errors.append(f"locators[{index}] có source/kind/label không hợp lệ")
            for start_key, end_key in (("start_char", "end_char"), ("timestamp_start_ms", "timestamp_end_ms")):
                start, end = row.get(start_key), row.get(end_key)
                if (start is None) != (end is None) or (start is not None and (type(start) is not int or type(end) is not int or start < 0 or end <= start)):
                    errors.append(f"locators[{index}] có khoảng {start_key}/{end_key} không hợp lệ")

    sections = document.get("sections")
    section_ids: set[str] = set()
    if not isinstance(sections, list) or not sections:
        errors.append("sections phải là array không rỗng")
    else:
        for index, row in enumerate(sections, 1):
            if not isinstance(row, Mapping) or set(row) != SECTION_FIELDS:
                errors.append(f"sections[{index}] không đúng closed schema")
                continue
            section_id = row.get("section_id")
            if not _id(section_id, "section") or section_id in section_ids:
                errors.append(f"sections[{index}].section_id không hợp lệ hoặc trùng")
            else:
                section_ids.add(section_id)
            if row.get("source_id") not in source_ids or not _text(row.get("summary")):
                errors.append(f"sections[{index}] có source/summary không hợp lệ")
            if not _string_list(row.get("locator_ids")) or not set(row.get("locator_ids", [])) <= locator_ids:
                errors.append(f"sections[{index}].locator_ids không hợp lệ")
            if not _string_list(row.get("key_points")) or not _string_list(row.get("uncertainties")):
                errors.append(f"sections[{index}] key_points/uncertainties không hợp lệ")

    claims = document.get("claims")
    claim_ids: set[str] = set()
    if not isinstance(claims, list):
        errors.append("claims phải là array")
    else:
        for index, row in enumerate(claims, 1):
            if not isinstance(row, Mapping) or set(row) != CLAIM_FIELDS:
                errors.append(f"claims[{index}] không đúng closed schema")
                continue
            claim_id = row.get("claim_id")
            if not _id(claim_id, "claim", 4) or claim_id in claim_ids:
                errors.append(f"claims[{index}].claim_id không hợp lệ hoặc trùng")
            else:
                claim_ids.add(claim_id)
            claim_type = row.get("claim_type")
            if not _text(row.get("statement")) or claim_type not in CLAIM_TYPES or row.get("confidence") not in CONFIDENCES or type(row.get("included_in_summary")) is not bool:
                errors.append(f"claims[{index}] có statement/type/confidence không hợp lệ")
            if not _string_list(row.get("source_ids")) or not set(row.get("source_ids", [])) <= source_ids:
                errors.append(f"claims[{index}].source_ids không hợp lệ")
            if not _string_list(row.get("locator_ids")) or not set(row.get("locator_ids", [])) <= locator_ids:
                errors.append(f"claims[{index}].locator_ids không hợp lệ")
            if claim_type == "SOURCE" and (not row.get("source_ids") or not row.get("locator_ids")):
                errors.append(f"claims[{index}] SOURCE cần source_ids và locator_ids")

    relations = document.get("claim_relations")
    if not isinstance(relations, list):
        errors.append("claim_relations phải là array")
    else:
        seen_relations: set[tuple[object, object, object]] = set()
        for index, row in enumerate(relations, 1):
            if not isinstance(row, Mapping) or set(row) != RELATION_FIELDS:
                errors.append(f"claim_relations[{index}] không đúng closed schema")
                continue
            relation = (row.get("from_claim_id"), row.get("type"), row.get("to_claim_id"))
            if relation in seen_relations or relation[0] not in claim_ids or relation[2] not in claim_ids or relation[1] not in RELATION_TYPES or relation[0] == relation[2]:
                errors.append(f"claim_relations[{index}] không hợp lệ hoặc trùng")
            seen_relations.add(relation)

    numeric_facts = document.get("numeric_facts")
    if not isinstance(numeric_facts, list):
        errors.append("numeric_facts phải là array")
    else:
        seen_numeric: set[str] = set()
        for index, row in enumerate(numeric_facts, 1):
            if not isinstance(row, Mapping) or set(row) != NUMERIC_FACT_FIELDS:
                errors.append(f"numeric_facts[{index}] không đúng closed schema")
                continue
            identifier, value = row.get("numeric_fact_id"), row.get("value")
            if not _id(identifier, "num", 4) or identifier in seen_numeric:
                errors.append(f"numeric_facts[{index}].numeric_fact_id không hợp lệ hoặc trùng")
            elif not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not _text(row.get("unit")):
                errors.append(f"numeric_facts[{index}] có value/unit không hợp lệ")
            seen_numeric.add(identifier) if isinstance(identifier, str) else None
            if not _string_list(row.get("locator_ids"), allow_empty=False) or not set(row.get("locator_ids", [])) <= locator_ids:
                errors.append(f"numeric_facts[{index}].locator_ids không hợp lệ")
            for field in ("population", "period"):
                if row.get(field) is not None and not _text(row.get(field)):
                    errors.append(f"numeric_facts[{index}].{field} không hợp lệ")

    glossary = document.get("glossary")
    if not isinstance(glossary, list):
        errors.append("glossary phải là array")
    else:
        seen_terms: set[str] = set()
        for index, row in enumerate(glossary, 1):
            if not isinstance(row, Mapping) or set(row) != GLOSSARY_FIELDS:
                errors.append(f"glossary[{index}] không đúng closed schema")
                continue
            term = row.get("term")
            if not _text(term) or str(term).casefold() in seen_terms or not _text(row.get("definition")) or type(row.get("do_not_translate")) is not bool:
                errors.append(f"glossary[{index}] không hợp lệ hoặc trùng")
            else:
                seen_terms.add(str(term).casefold())
            if row.get("original_term") is not None and not _text(row.get("original_term")):
                errors.append(f"glossary[{index}].original_term không hợp lệ")
            if not _string_list(row.get("locator_ids")) or not set(row.get("locator_ids", [])) <= locator_ids:
                errors.append(f"glossary[{index}].locator_ids không hợp lệ")

    narration = document.get("narration")
    if not isinstance(narration, list) or not narration:
        errors.append("narration phải là array không rỗng")
    else:
        seen: set[str] = set()
        for index, row in enumerate(narration, 1):
            if not isinstance(row, Mapping) or set(row) != NARRATION_FIELDS:
                errors.append(f"narration[{index}] không đúng closed schema")
                continue
            expected = f"narration_{index:04d}"
            if row.get("narration_id") != expected or expected in seen:
                errors.append(f"narration[{index}].narration_id phải là {expected}")
            seen.add(expected)
            if row.get("section_id") not in section_ids or not _text(row.get("text")):
                errors.append(f"narration[{index}] có section/text không hợp lệ")
            if not _string_list(row.get("claim_ids")) or not set(row.get("claim_ids", [])) <= claim_ids:
                errors.append(f"narration[{index}].claim_ids không hợp lệ")
    if not _string_list(document.get("limitations")):
        errors.append("limitations phải là array string duy nhất")
    return errors


__all__ = ["validate_summary_document"]
