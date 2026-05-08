from __future__ import annotations

from statistics import median
from typing import Any

from story.gui.history_utils import append_timestamped_history_entry

from .state import STORY_DRAFT_HISTORY_KEY, STORY_LAST_HISTORY_KEY, STORY_OUTLINE_HISTORY_KEY, ensure_session_defaults


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def append_history(result: dict[str, Any]) -> None:
    ensure_session_defaults()
    title = (((result.get('authoring') or {}).get('meta') or {}).get('title') or 'story').strip() or 'story'
    append_timestamped_history_entry(
        STORY_LAST_HISTORY_KEY,
        {
            'title': title,
            'mode': result.get('mode'),
            'script_items': len((result.get('authoring') or {}).get('script') or []),
        },
        limit=12,
    )


def append_outline_history(
    *,
    elapsed_s: float,
    target_duration_min: int | None,
    mode: str,
    max_tokens: int,
    state: dict[str, Any] | None = None,
) -> None:
    append_timestamped_history_entry(
        STORY_OUTLINE_HISTORY_KEY,
        {
            "elapsed_s": round(max(0.0, float(elapsed_s)), 2),
            "target_duration_min": target_duration_min,
            "mode": mode,
            "max_tokens": max_tokens,
        },
        limit=20,
        state=state,
    )


def append_draft_history(
    *,
    elapsed_s: float,
    target_duration_min: int | None,
    mode: str,
    max_tokens: int,
    chunked: bool,
    chunk_size: int,
    state: dict[str, Any] | None = None,
) -> None:
    append_timestamped_history_entry(
        STORY_DRAFT_HISTORY_KEY,
        {
            "elapsed_s": round(max(0.0, float(elapsed_s)), 2),
            "target_duration_min": target_duration_min,
            "mode": mode,
            "max_tokens": max_tokens,
            "chunked": chunked,
            "chunk_size": chunk_size,
        },
        limit=20,
        state=state,
    )


def estimate_phase_seconds(target_duration_min: int | None, history: list[dict[str, Any]]) -> tuple[float | None, int]:
    valid = [entry for entry in history if isinstance(entry, dict) and _positive_float(entry.get("elapsed_s")) is not None]
    if not valid:
        return None, 0

    target = _positive_float(target_duration_min)
    if target is not None:
        ratios = []
        for entry in valid:
            elapsed = _positive_float(entry.get("elapsed_s"))
            previous_target = _positive_float(entry.get("target_duration_min"))
            if elapsed is not None and previous_target is not None:
                ratios.append(elapsed / previous_target)
        if ratios:
            return median(ratios[:8]) * target, len(ratios)

    elapsed_values = [_positive_float(entry.get("elapsed_s")) for entry in valid]
    usable_elapsed = [value for value in elapsed_values if value is not None]
    return median(usable_elapsed[:8]), len(usable_elapsed)


def estimate_outline_seconds(target_duration_min: int | None, history: list[dict[str, Any]]) -> tuple[float | None, int]:
    return estimate_phase_seconds(target_duration_min, history)


def estimate_draft_seconds(target_duration_min: int | None, history: list[dict[str, Any]]) -> tuple[float | None, int]:
    return estimate_phase_seconds(target_duration_min, history)
