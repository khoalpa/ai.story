from __future__ import annotations

from typing import Any, Iterable


def format_duration(seconds: float | int | None) -> str:
    value = max(0, int(round(float(seconds or 0))))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def compact_detail(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value).strip()


def join_details(details: Iterable[str]) -> str:
    return " | ".join(detail for detail in (compact_detail(item) for item in details) if detail)


def format_progress_text(percent: int | float, message: str, details: Iterable[str] = ()) -> str:
    pct = max(0, min(100, int(round(float(percent or 0)))))
    base = str(message or "Processing").strip()
    suffix = join_details(details)
    return f"{pct}% - {base}" + (f" | {suffix}" if suffix else "")


def summarize_progress_details(summary: dict[str, Any] | None) -> str:
    if not isinstance(summary, dict) or not summary:
        return ""

    preferred_keys = (
        "mode",
        "provider",
        "audio_format",
        "generated",
        "prompt_count",
        "script_items",
        "image_prompts",
        "aspect",
        "title",
    )
    details: list[str] = []
    for key in preferred_keys:
        value = summary.get(key)
        if value not in (None, ""):
            details.append(f"{key}={compact_detail(value)}")
    return join_details(details[:4])
