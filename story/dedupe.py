from __future__ import annotations

import re
from typing import Any, Dict, List

from .normalization import sanitize_spoken_text


def _normalize_text_for_dedupe(text: Any) -> str:
    s = sanitize_spoken_text(text).lower()
    s = re.sub(r"[\"'“”‘’()\[\]{}<>]", " ", s)
    s = re.sub(r"[^\w\sÀ-ỹ]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokenize_for_dedupe(text: Any) -> List[str]:
    s = _normalize_text_for_dedupe(text)
    if not s:
        return []
    return [tok for tok in s.split() if tok]


def _signature_for_exact_dedupe(text: Any) -> str:
    return _normalize_text_for_dedupe(text)


def _jaccard_similarity(a_tokens: List[str], b_tokens: List[str]) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    a_set = set(a_tokens)
    b_set = set(b_tokens)
    union = a_set | b_set
    if not union:
        return 0.0
    return len(a_set & b_set) / len(union)


def _is_low_value_text(text: Any) -> bool:
    raw = sanitize_spoken_text(text)
    norm = _normalize_text_for_dedupe(text)
    if not norm:
        return True
    tokens = norm.split()
    if len(tokens) <= 2:
        low_value_terms = {
            "calming", "peaceful", "narrative", "storytelling", "relaxing",
            "gentle", "soft", "quiet", "sleep", "bedtime",
            "êm", "dịu", "nhẹ", "yên", "tĩnh", "thư", "giãn",
        }
        if all(tok in low_value_terms for tok in tokens):
            return True
    alpha_count = len(re.findall(r"[A-Za-zÀ-ỹ]", raw))
    return alpha_count < 3


def dedupe_script_items(items: Any, *, exact_window: int = 0, near_window: int = 12, similarity_threshold: float = 0.88, max_occurrences_per_signature: int = 2) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    kept: List[Dict[str, Any]] = []
    global_seen: Dict[str, int] = {}

    for raw_item in items:
        if isinstance(raw_item, str):
            item = {"text": raw_item}
        elif isinstance(raw_item, dict):
            item = dict(raw_item)
        else:
            continue

        text = sanitize_spoken_text(item.get("text", ""))
        if not text or _is_low_value_text(text):
            continue
        signature = _signature_for_exact_dedupe(text)
        if not signature:
            continue

        zone_key = str(item.get("zone", "")).strip() or "__ANY_ZONE__"
        zone_signature = f"{zone_key}::{signature}"
        if global_seen.get(zone_signature, 0) >= max_occurrences_per_signature:
            continue

        candidate_tokens = _tokenize_for_dedupe(text)
        is_duplicate = False
        haystack = kept[-exact_window:] if exact_window > 0 and kept else kept
        for prev in haystack:
            prev_sig = _signature_for_exact_dedupe(prev.get("text", ""))
            prev_zone = str(prev.get("zone", "")).strip() or "__ANY_ZONE__"
            if prev_sig == signature and prev_zone == zone_key:
                is_duplicate = True
                break
        if is_duplicate:
            continue

        if near_window > 0 and kept and candidate_tokens:
            for prev in kept[-near_window:]:
                prev_zone = str(prev.get("zone", "")).strip() or "__ANY_ZONE__"
                if prev_zone != zone_key:
                    continue
                prev_tokens = _tokenize_for_dedupe(prev.get("text", ""))
                if prev_tokens and _jaccard_similarity(candidate_tokens, prev_tokens) >= similarity_threshold:
                    is_duplicate = True
                    break
        if is_duplicate:
            continue

        item["text"] = text
        kept.append(item)
        global_seen[zone_signature] = global_seen.get(zone_signature, 0) + 1
    return kept


def dedupe_authoring_script_inplace(obj: Dict[str, Any], *, exact_window: int = 0, near_window: int = 12, similarity_threshold: float = 0.88, max_occurrences_per_signature: int = 2) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return
    obj["script"] = dedupe_script_items(
        script,
        exact_window=exact_window,
        near_window=near_window,
        similarity_threshold=similarity_threshold,
        max_occurrences_per_signature=max_occurrences_per_signature,
    )
