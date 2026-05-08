from __future__ import annotations

import re
from typing import Any, Dict, List

from .audio_story_spec import _looks_like_single_sentence
from .normalization import sanitize_spoken_text, split_text_into_sentences




def _split_strict_sentence_boundaries(text: Any) -> List[str]:
    s = sanitize_spoken_text(text)
    if not s:
        return []

    parts: List[str] = []
    start = 0
    n = len(s)
    i = 0
    while i < n:
        ch = s[i]
        if ch not in ".!?…":
            i += 1
            continue

        j = i + 1
        while j < n and s[j] in '"\'”’）)]}':
            j += 1

        next_ch = s[j] if j < n else ""
        if next_ch and not next_ch.isspace():
            i += 1
            continue

        chunk = s[start:j].strip()
        if chunk:
            parts.append(chunk)
        start = j
        i = j

    tail = s[start:].strip()
    if tail:
        parts.append(tail)

    normalized: List[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip()
        if not part:
            continue
        if part[-1] not in ".!?…":
            part = f"{part}."
        normalized.append(part)
    return normalized


def _truncate_to_first_sentence(text: Any) -> str:
    s = sanitize_spoken_text(text)
    if not s:
        return ""
    for idx, ch in enumerate(s):
        if ch in ".!?…":
            end = idx + 1
            while end < len(s) and s[end] in '"\'”’）)]}':
                end += 1
            out = s[:end].strip()
            if out:
                return out
    return s if s[-1] in ".!?…" else f"{s}."


def _ensure_single_sentence_parts(text: Any) -> List[str]:
    parts = split_text_into_sentences(text)
    if not parts:
        return []

    ensured: List[str] = []
    for part in parts:
        candidate = sanitize_spoken_text(part)
        if not candidate:
            continue
        if _looks_like_single_sentence(candidate):
            ensured.append(candidate)
            continue

        strict_parts = _split_strict_sentence_boundaries(candidate)
        if strict_parts and any(x != candidate for x in strict_parts):
            for strict in strict_parts:
                strict = sanitize_spoken_text(strict)
                if strict and _looks_like_single_sentence(strict):
                    ensured.append(strict)
            if ensured:
                continue

        fallback = _truncate_to_first_sentence(candidate)
        if fallback:
            ensured.append(fallback)

    return ensured

def repair_authoring_single_sentence_inplace(obj: Dict[str, Any]) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return

    repaired: List[Dict[str, Any]] = []
    for item in script:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict):
            continue

        zone = str(item.get("zone", "")).strip() or "GIỚI THIỆU"
        environment = str(item.get("environment", "")).strip()
        voice = str(item.get("voice", "NARRATOR")).strip() or "NARRATOR"
        speed = str(item.get("speed", "NORMAL")).strip() or "NORMAL"
        lang = str(item.get("lang", "VI")).strip() or "VI"

        sentences = _ensure_single_sentence_parts(item.get("text", ""))
        if not sentences:
            continue

        for sentence in sentences:
            cloned = dict(item)
            cloned["zone"] = zone
            cloned["environment"] = environment
            cloned["voice"] = voice
            cloned["speed"] = speed
            cloned["lang"] = lang
            cloned["text"] = sentence
            repaired.append(cloned)

    obj["script"] = repaired


def force_single_sentence_items_inplace(obj: Dict[str, Any]) -> None:
    repair_authoring_single_sentence_inplace(obj)
