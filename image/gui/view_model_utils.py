from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping


def path_to_text(value: str | Path | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def pick_mapping_values(source: Mapping[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {field: source.get(field) for field in fields}


def pick_session_state_values(state: Mapping[str, Any], fields: Iterable[str], *, strip_text: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in fields:
        value = state.get(field)
        if strip_text and isinstance(value, str):
            payload[field] = value.strip()
        else:
            payload[field] = value
    return payload
