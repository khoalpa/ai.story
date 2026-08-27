from __future__ import annotations

import unicodedata


def normalize_voice_token(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d").replace("Đ", "D")
    return " ".join(text.strip().lower().split())


LEGACY_VIENEU_VOICE_HINTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "vi-vn-hoaimyneural": (("doan",), ("truc", "ly"), ("female", "south")),
    "vi-vn-namminhneural": (("vinh",), ("male", "south")),
    "en-us-guyneural": (("binh",), ("male", "north")),
    "doan": (("doan",), ("nu", "mien", "nam"), ("female", "south")),
    "thuc doan": (("doan",), ("nu", "mien", "nam"), ("female", "south")),
    "ly": (("ly",), ("nu", "mien", "bac"), ("female", "north")),
    "ngoc": (("ngoc",), ("nu", "mien", "bac"), ("female", "north")),
    "bich ngoc": (("ngoc",), ("nu", "mien", "bac"), ("female", "north")),
    "vinh": (("vinh",), ("nam", "mien", "nam"), ("male", "south")),
    "xuan vinh": (("vinh",), ("nam", "mien", "nam"), ("male", "south")),
    "binh": (("binh",), ("nam", "mien", "bac"), ("male", "north")),
    "tuyen": (("tuyen",), ("nam", "mien", "bac"), ("male", "north")),
    "pham tuyen": (("tuyen",), ("nam", "mien", "bac"), ("male", "north")),
}


def migrate_vieneu_legacy_voice_id(
    voice_id: object,
    available_choices: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> str:
    raw = str(voice_id or "").strip()
    if not raw:
        return ""
    normalized = normalize_voice_token(raw)
    if not normalized:
        return raw

    entries: list[tuple[str, str, str, str, set[str]]] = []
    for label, preset_id in tuple(available_choices or ()):
        clean_id = str(preset_id or "").strip()
        clean_label = str(label or clean_id).strip()
        if not clean_id:
            continue
        norm_id = normalize_voice_token(clean_id)
        norm_label = normalize_voice_token(clean_label)
        entries.append((clean_id, clean_label, norm_id, norm_label, set((norm_id + " " + norm_label).split())))

    if not entries:
        return raw
    for clean_id, _clean_label, norm_id, norm_label, _tokens in entries:
        if normalized in {norm_id, norm_label, normalize_voice_token(norm_label.split("(", 1)[0].strip())}:
            return clean_id

    hint_groups = LEGACY_VIENEU_VOICE_HINTS.get(normalized)
    if not hint_groups:
        return raw
    ranked: list[tuple[int, str]] = []
    for clean_id, _clean_label, _norm_id, _norm_label, tokens in entries:
        score = 100 if normalized in tokens else 0
        for idx, group in enumerate(hint_groups):
            group_tokens = {token for token in map(normalize_voice_token, group) if token}
            if group_tokens.issubset(tokens):
                score += 30 - idx * 5
            elif any(token in tokens for token in group_tokens):
                score += 8 - idx
        if score > 0:
            ranked.append((score, clean_id))
    if not ranked:
        return raw
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1]
