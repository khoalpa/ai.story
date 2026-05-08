from __future__ import annotations

import re
from typing import Any, Dict, List

from .audio_story_spec import ALLOWED_SCRIPT_ZONES, canonical_script_zone_label
from .common import _SENTENCE_END_RE


def sanitize_spoken_text(text: Any) -> str:
    t = "" if text is None else str(text)
    t = t.replace("[", "(").replace("]", ")")
    t = t.replace("{", "(").replace("}", ")")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _looks_like_abbreviation_tail(left: str) -> bool:
    left = (left or "").rstrip()
    if not left:
        return False
    tokens = left.split()
    tail = tokens[-1] if tokens else ""
    tail_lower = tail.lower()
    common = {
        "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
        "tp.", "q.", "p.", "ts.", "ths.", "pgs.", "gs.",
        "vd.", "v.v.", "etc.", "eg.", "i.e.", "no.", "st.",
    }
    if tail_lower in common:
        return True
    if re.fullmatch(r"(?:[A-Za-zÀ-ỹ]\.){2,}", tail):
        return True
    if re.fullmatch(r"\d+\.", tail):
        return True
    return False


def split_text_into_sentences(text: Any) -> List[str]:
    s = sanitize_spoken_text(text)
    if not s:
        return []

    parts: List[str] = []
    buf: List[str] = []
    n = len(s)

    for i, ch in enumerate(s):
        buf.append(ch)
        if ch not in ".!?…":
            continue

        current = "".join(buf)
        if _looks_like_abbreviation_tail(current[:-1]):
            continue

        j = i + 1
        while j < n and s[j] in '"\'”’）)]}':
            buf.append(s[j])
            j += 1

        next_ch = s[j] if j < n else ""
        if next_ch and not next_ch.isspace():
            continue

        sentence = "".join(buf).strip()
        if sentence:
            parts.append(sentence)
        buf = []

    rest = "".join(buf).strip()
    if rest:
        if parts:
            parts[-1] = f"{parts[-1]} {rest}".strip()
        else:
            parts.append(rest)

    normalized: List[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip()
        if not part:
            continue
        if not _SENTENCE_END_RE.search(part):
            part = f"{part}."
        normalized.append(part)

    return normalized


def normalize_chunk_items_to_single_sentence(arr: Any, zone: str, speed: str, lang_tag: str) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    if not isinstance(arr, list):
        return normalized

    canonical_zone = canonical_script_zone_label(zone)

    for item in arr:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("text", "")
        else:
            continue

        sentences = split_text_into_sentences(text)
        for sentence in sentences:
            normalized.append({
                "zone": canonical_zone,
                "environment": "",
                "voice": "NARRATOR",
                "speed": speed,
                "lang": lang_tag,
                "text": sentence,
            })
    return normalized


def _validator_sentence_parts(text: Any) -> List[str]:
    return split_text_into_sentences(text)


def coerce_text_to_single_sentence(text: Any) -> str:
    parts = _validator_sentence_parts(text)
    if not parts:
        return ""
    return parts[0]


def ensure_script_zone_order_inplace(obj: dict) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return

    buckets: dict[str, list[dict]] = {zone: [] for zone in ALLOWED_SCRIPT_ZONES}
    invalid: list[dict] = []
    for item in script:
        if not isinstance(item, dict):
            continue
        zone = canonical_script_zone_label(item.get("zone"))
        item["zone"] = zone
        if zone in buckets:
            buckets[zone].append(item)
        else:
            invalid.append(item)

    ordered: list[dict] = []
    for zone in ALLOWED_SCRIPT_ZONES:
        ordered.extend(buckets[zone])
    ordered.extend(invalid)
    obj["script"] = ordered


def sanitize_authoring_inplace(obj: dict) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return
    for item in script:
        if not isinstance(item, dict):
            continue
        item["zone"] = canonical_script_zone_label(item.get("zone"))
        item.setdefault("environment", "")
        if item.get("environment") is None:
            item["environment"] = ""
        if "text" in item:
            item["text"] = sanitize_spoken_text(item.get("text"))
    ensure_script_zone_order_inplace(obj)
