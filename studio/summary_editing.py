"""Validated immutable edits for canonical Summary documents."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from studio.summary_schema import validate_summary_document


def _validated(document: dict[str, Any]) -> dict[str, Any]:
    errors = validate_summary_document(document)
    if errors:
        raise ValueError("Chỉnh sửa không hợp lệ: " + "; ".join(errors))
    return document


def update_summary_meta(document: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(document))
    unknown = set(changes) - set(result["meta"])
    if unknown:
        raise ValueError("Meta field không hỗ trợ: " + ", ".join(sorted(unknown)))
    result["meta"].update(changes)
    return _validated(result)


def replace_summary_rows(
    document: Mapping[str, Any], field: str, rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if field not in {"claims", "claim_relations", "numeric_facts", "glossary", "narration"}:
        raise ValueError(f"Không hỗ trợ chỉnh bảng: {field}")
    result = deepcopy(dict(document))
    result[field] = [dict(row) for row in rows]
    return _validated(result)


__all__ = ["replace_summary_rows", "update_summary_meta"]
