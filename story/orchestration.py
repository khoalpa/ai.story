from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from .audio_story_spec import ALLOWED_SCRIPT_ZONES, OUTLINE_KEYS, canonical_script_zone_label
from .dedupe import (
    _jaccard_similarity,
    _normalize_text_for_dedupe,
    _signature_for_exact_dedupe,
    _tokenize_for_dedupe,
    dedupe_authoring_script_inplace,
)
from .normalization import sanitize_authoring_inplace, sanitize_spoken_text, split_text_into_sentences
from .repair import force_single_sentence_items_inplace, repair_authoring_single_sentence_inplace




def _restore_missing_canonical_zones_inplace(obj: Dict[str, Any], source_script: List[Dict[str, Any]]) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return

    existing = {canonical_script_zone_label((item or {}).get("zone")) for item in script if isinstance(item, dict)}
    missing = [zone for zone in ALLOWED_SCRIPT_ZONES if zone not in existing]
    if not missing:
        return

    fallback_by_zone: Dict[str, Dict[str, Any]] = {}
    for item in source_script:
        if not isinstance(item, dict):
            continue
        zone = canonical_script_zone_label(item.get("zone"))
        if zone in ALLOWED_SCRIPT_ZONES and zone not in fallback_by_zone:
            cloned = dict(item)
            cloned["zone"] = zone
            cloned.setdefault("environment", "")
            fallback_by_zone[zone] = cloned

    restored: List[Dict[str, Any]] = list(script)
    for zone in missing:
        fallback = fallback_by_zone.get(zone)
        if fallback is not None:
            restored.append(dict(fallback))

    zone_order = {zone: idx for idx, zone in enumerate(ALLOWED_SCRIPT_ZONES)}
    restored.sort(key=lambda item: (zone_order.get(canonical_script_zone_label((item or {}).get("zone")), 10**9),))
    obj["script"] = restored

def _iter_outline_sentences(authoring: Dict[str, Any]) -> List[str]:
    outline = authoring.get("outline") if isinstance(authoring, dict) else None
    if not isinstance(outline, dict):
        return []
    out: List[str] = []
    for key in OUTLINE_KEYS:
        value = outline.get(key)
        if isinstance(value, str) and value.strip():
            out.extend(split_text_into_sentences(value))
    return [x for x in out if x]


def _zone_key(item: Dict[str, Any]) -> str:
    return str((item or {}).get("zone", "")).strip()


def prune_zone_misplaced_boilerplate_inplace(obj: Dict[str, Any]) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return
    greeting_only_patterns = [r"\baudio\s*story\b", r"\bkênh\b", r"\bchương\s*trình\b", r"\bpodcast\b", r"\bchào\s*mừng\b"]
    farewell_only_patterns = [r"\bhẹn\s*gặp\s*lại\b", r"\btạm\s*biệt\b", r"\bcảm\s*ơn\s*(bạn|mọi người|đã lắng nghe)?\b", r"\bthanks?\b", r"\bsee\s+you\b"]
    kept: List[Dict[str, Any]] = []
    for item in script:
        if not isinstance(item, dict):
            continue
        zone = _zone_key(item)
        text = sanitize_spoken_text(item.get("text", ""))
        norm = _normalize_text_for_dedupe(text)
        if not norm:
            continue
        if zone != "LỜI CHÀO" and any(re.search(p, norm, flags=re.IGNORECASE) for p in greeting_only_patterns):
            continue
        if zone != "TẠM BIỆT" and any(re.search(p, norm, flags=re.IGNORECASE) for p in farewell_only_patterns):
            continue
        kept.append(item)
    obj["script"] = kept


def prune_outline_echoes_inplace(obj: Dict[str, Any], *, similarity_threshold: float = 0.84, max_occurrences_per_outline_signature: int = 1) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return
    outline_sentences = _iter_outline_sentences(obj)
    if not outline_sentences:
        return
    outline_sigs = []
    for sent in outline_sentences:
        sig = _signature_for_exact_dedupe(sent)
        toks = _tokenize_for_dedupe(sent)
        if sig and toks:
            outline_sigs.append((sig, toks))
    counts: Dict[str, int] = {}
    kept: List[Dict[str, Any]] = []
    for item in script:
        if not isinstance(item, dict):
            continue
        text = sanitize_spoken_text(item.get("text", ""))
        sig = _signature_for_exact_dedupe(text)
        toks = _tokenize_for_dedupe(text)
        if not sig or not toks:
            continue
        matched_outline_sig = None
        for osig, otoks in outline_sigs:
            sim = _jaccard_similarity(toks, otoks)
            if sig == osig or sim >= similarity_threshold:
                matched_outline_sig = osig
                break
        if matched_outline_sig is not None:
            seen = counts.get(matched_outline_sig, 0)
            if seen >= max_occurrences_per_outline_signature:
                continue
            counts[matched_outline_sig] = seen + 1
        kept.append(item)
    obj["script"] = kept


def _learn_motif_aliases_from_authoring(obj: Dict[str, Any]) -> Dict[str, Set[str]]:
    stop = {
        "một","những","các","và","là","của","trong","ngoài","giữa","với","cho","đến","ở","về","khi","đó","này","ấy","rất","đang","đã","sẽ","được",
        "the","a","an","and","or","of","to","in","on","at","for","with","from","that","this","is","are","was","were","be",
        "người","câu","chuyện","đêm","ngày","city","story",
    }
    texts: List[str] = []
    if isinstance(obj, dict):
        meta = obj.get("meta")
        if isinstance(meta, dict):
            for key in ("title", "genre", "tone", "audience", "target"):
                val = meta.get(key)
                if isinstance(val, str) and val.strip():
                    texts.append(val)
        outline = obj.get("outline")
        if isinstance(outline, dict):
            for key in OUTLINE_KEYS:
                val = outline.get(key)
                if isinstance(val, str) and val.strip():
                    texts.append(val)
    def toks(s: str) -> List[str]:
        return [t for t in _tokenize_for_dedupe(s) if len(t) >= 2 and t not in stop]
    phrases: List[List[str]] = []
    for text in texts:
        tokens = toks(text)
        for n in (3, 2, 1):
            for i in range(0, max(0, len(tokens) - n + 1)):
                gram = tokens[i : i + n]
                if len(gram) == 1 and len(gram[0]) < 4:
                    continue
                phrases.append(gram)
    clusters: Dict[str, Set[str]] = {
        "quán_cà_phê": {"quán", "quán nhỏ", "quán quen", "quán cà phê", "tiệm cà phê", "cà phê", "cafe", "quán cafe", "tiệm cafe"},
        "chiếc_cúp": {"chiếc cúp", "cái cúp", "cúp"},
        "giấc_mơ": {"giấc mơ", "ước mơ", "mơ ước"},
        "guitar_âm_nhạc": {"guitar", "tiếng đàn", "âm nhạc", "giai điệu"},
        "thành_phố_đêm": {"thành phố", "phố đêm", "đêm thành phố", "city lights", "đèn thành phố"},
        "clip_mạng_xã_hội": {"clip", "đoạn clip", "video ngắn", "lượt xem", "thông báo", "mạng xã hội"},
    }
    learned: Dict[frozenset[str], Set[str]] = {}
    for gram in phrases:
        core = tuple(sorted(dict.fromkeys(gram)))
        if core:
            learned.setdefault(frozenset(core), set()).add(" ".join(gram))
    for learned_core, aliases in learned.items():
        target = None
        core_set: Set[str] = set(learned_core)
        if {"quán", "cà", "phê"} <= core_set or "cafe" in core_set or "quán" in core_set:
            target = "quán_cà_phê"
        elif "cúp" in core_set:
            target = "chiếc_cúp"
        elif "mơ" in core_set:
            target = "giấc_mơ"
        elif "guitar" in core_set or "nhạc" in core_set or "điệu" in core_set:
            target = "guitar_âm_nhạc"
        elif "thành" in core_set or "phố" in core_set or "city" in core_set or "đèn" in core_set:
            target = "thành_phố_đêm"
        elif "clip" in core_set or "video" in core_set or "xem" in core_set or "mạng" in core_set or "thông" in core_set:
            target = "clip_mạng_xã_hội"
        elif len(core_set) >= 2:
            target = "_".join(sorted(core_set)[:3])
        if target:
            clusters.setdefault(target, set()).update(aliases)
            clusters[target].add(" ".join(sorted(core_set)))
    return clusters


def _extract_motif_clusters(text: Any, learned_aliases: Dict[str, Set[str]] | None = None) -> Set[str]:
    norm = _normalize_text_for_dedupe(text)
    if not norm:
        return set()
    found: Set[str] = set()
    for family, family_aliases in (learned_aliases or {}).items():
        for alias in family_aliases:
            a = _normalize_text_for_dedupe(alias)
            if a and a in norm:
                found.add(family)
                break
    tokens = _tokenize_for_dedupe(norm)
    for n in (2, 3):
        for i in range(0, max(0, len(tokens) - n + 1)):
            gram = tokens[i : i + n]
            if len(" ".join(gram)) >= 8:
                found.add(" ".join(gram))
    return found


def _zone_motif_cap(zone: str) -> int:
    return {"LỜI CHÀO": 1, "TẠM BIỆT": 1, "TRIỂN KHAI": 2}.get(zone, 2)


def semantic_motif_cap_inplace(obj: Dict[str, Any], *, near_window: int = 10, similarity_threshold: float = 0.82) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return
    learned_aliases = _learn_motif_aliases_from_authoring(obj)
    seen_by_zone: Dict[str, Dict[str, int]] = {}
    kept: List[Dict[str, Any]] = []
    for item in script:
        if not isinstance(item, dict):
            continue
        zone = _zone_key(item)
        text = sanitize_spoken_text(item.get("text", ""))
        if not text:
            continue
        motifs = _extract_motif_clusters(text, learned_aliases)
        zmap = seen_by_zone.setdefault(zone, {})
        cap = _zone_motif_cap(zone)
        over_cap = [m for m in motifs if zmap.get(m, 0) >= cap]
        if over_cap:
            cand_tokens = _tokenize_for_dedupe(text)
            duplicate_like = False
            for prev in kept[-near_window:]:
                if _zone_key(prev) != zone:
                    continue
                if _jaccard_similarity(cand_tokens, _tokenize_for_dedupe(prev.get("text", ""))) >= similarity_threshold:
                    duplicate_like = True
                    break
                if _extract_motif_clusters(prev.get("text", ""), learned_aliases).intersection(over_cap):
                    duplicate_like = True
                    break
            if duplicate_like:
                continue
        kept.append(item)
        for motif in motifs:
            zmap[motif] = zmap.get(motif, 0) + 1
    obj["script"] = kept


def prune_story_drift_inplace(obj: Dict[str, Any], *, max_unanchored_ratio: float = 0.85) -> None:
    if not isinstance(obj, dict):
        return
    script = obj.get("script")
    if not isinstance(script, list):
        return
    learned_aliases = _learn_motif_aliases_from_authoring(obj)
    anchor_tokens: Set[str] = set()
    for aliases in learned_aliases.values():
        for alias in aliases:
            for tok in _tokenize_for_dedupe(alias):
                if len(tok) >= 3:
                    anchor_tokens.add(tok)
    english_drift = {"welcome", "channel", "podcast", "storytelling", "narrative", "heart of", "board"}
    subplot_markers = [r"\bcó\s+một\s+cô\s+bé\b", r"\bcó\s+một\s+cậu\s+bé\b", r"\bở\s+một\s+nơi\s+khác\b", r"\bxuất\s+hiện\s+một\b"]
    kept: List[Dict[str, Any]] = []
    for item in script:
        if not isinstance(item, dict):
            continue
        text = sanitize_spoken_text(item.get("text", ""))
        norm = _normalize_text_for_dedupe(text)
        toks = _tokenize_for_dedupe(text)
        if not norm:
            continue
        if any(marker in norm for marker in english_drift):
            continue
        if any(re.search(p, norm, flags=re.IGNORECASE) for p in subplot_markers) and len(set(toks) & anchor_tokens) <= 1:
            continue
        if toks and anchor_tokens:
            overlap_ratio = len(set(toks) & anchor_tokens) / max(1, len(set(toks)))
            if overlap_ratio < (1.0 - max_unanchored_ratio) and len(toks) >= 8:
                continue
        kept.append(item)
    obj["script"] = kept


def post_process_authoring(authoring: Dict[str, Any]) -> Dict[str, Any]:
    source_script = [dict(item) for item in (authoring.get("script") or []) if isinstance(item, dict)] if isinstance(authoring, dict) else []
    sanitize_authoring_inplace(authoring)
    repair_authoring_single_sentence_inplace(authoring)
    force_single_sentence_items_inplace(authoring)
    dedupe_authoring_script_inplace(authoring, exact_window=0, near_window=12, similarity_threshold=0.88, max_occurrences_per_signature=2)
    prune_zone_misplaced_boilerplate_inplace(authoring)
    prune_outline_echoes_inplace(authoring)
    prune_story_drift_inplace(authoring)
    semantic_motif_cap_inplace(authoring)
    dedupe_authoring_script_inplace(authoring, exact_window=0, near_window=12, similarity_threshold=0.88, max_occurrences_per_signature=2)
    force_single_sentence_items_inplace(authoring)
    _restore_missing_canonical_zones_inplace(authoring, source_script)
    return authoring
