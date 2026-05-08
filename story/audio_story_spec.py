#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audio_story_spec.py

Module trung tâm khai báo SPEC / CONSTANTS dùng chung cho:
- validate_plain_script.py
- make_audio_edge_tts.py
và các module khác của Audio Story dùng chung contract render/validation.

Mục tiêu:
- Tránh trùng lặp TAG_PATTERN, VOICE_TAGS, ZONE_KEYWORDS...
- Đảm bảo thay đổi spec ở một nơi duy nhất.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

###############################################################################
# TAG & VOICE SPEC
###############################################################################

# Pattern tìm tất cả [TAG] trong một dòng
TAG_PATTERN = re.compile(r"\[([^\]]+)\]")

# Các voice tag được hỗ trợ (đồng bộ với validate_plain_script.py hiện tại)
# Key: dạng tag (đã UPPERCASE, đã lấy "từ đầu" của tag)
# Value: role canonical dùng trong engine: "narrator" | "female" | "male"
VOICE_BASE_TAGS: Dict[str, str] = {
    "NARRATOR": "narrator",
    "NAR": "narrator",
    "MC": "narrator",
    "DANCHUYEN": "narrator",

    "F": "female",
    "FEMALE": "female",
    "NU": "female",

    "M": "male",
    "MALE": "male",
    "NAM": "male",
}

# Các role canonical hợp lệ cho voice
VOICE_ROLES: Tuple[str, ...] = ("narrator", "female", "male")

# Các tag kỹ thuật hợp lệ (không phải voice)
TECHNICAL_TAG_PREFIXES: Tuple[str, ...] = (
    "SFX",      # [SFX=...] hiệu ứng âm thanh
    "MUSIC",    # [MUSIC=...] chèn đoạn nhạc / hiệu ứng riêng
    "BGM",      # BGM, BGM=..., BGM_OFF...
    "BGM_DB",   # BGM_DB=...
    "RATE",     # RATE=...
    "SLOW",     #
    "FAST",     #
    "NORMAL",   #
    "PAUSE",    #
    "SILENCE",  #
    "VI",       # Ép giọng Việt cho dòng
    "EN",       # Ép giọng English cho dòng
)


LEGACY_UNSUPPORTED_TAGS: Tuple[str, ...] = (
    "BGMVOL",
    "BGM_VOLUME",
    "VOLUME",
)

###############################################################################
# ZONE SPEC
###############################################################################

# Zone keywords (comment bắt đầu bằng //) – cần đúng 8 zone của plain engine script
ZONE_KEYWORDS: Dict[str, List[str]] = {
    "greeting": ["LỜI CHÀO", "LOI CHAO", "GREETING"],
    "opening": ["MỞ TRUYỆN", "MO TRUYEN", "MỞ ĐẦU", "MO DAU", "OPENING", "INTRO"],
    "introduction": ["GIỚI THIỆU", "GIOI THIEU", "INTRODUCTION"],
    "development": ["TRIỂN KHAI", "TRIEN KHAI", "DEVELOPMENT"],
    "climax": ["CAO TRÀO", "CAO TRAO", "CLIMAX"],
    "falling": ["HẠ MÀN", "HA MAN", "FALLING"],
    "ending": ["KẾT TRUYỆN", "KET TRUYEN", "ENDING"],
    "farewell": ["TẠM BIỆT", "TAM BIET", "FAREWELL"],
}

# Thứ tự chuẩn của 8 zone (dùng cho validator nếu muốn kiểm tra thứ tự)
ZONE_ORDER: Tuple[str, ...] = (
    "greeting",
    "opening",
    "introduction",
    "development",
    "climax",
    "falling",
    "ending",
    "farewell",
)

###############################################################################
# HELPER FUNCTIONS DÙNG CHUNG
###############################################################################

def extract_base_token(tag: str) -> str:
    """
    Lấy token đầu tiên trong tag để nhận biết loại giọng hoặc loại tag.

    Ví dụ:
        "NARRATOR – GIỌNG DẪN" -> "NARRATOR"
        "MALE – MINH"          -> "MALE"
        "FEMALE - LAN"         -> "FEMALE"
        "NARRATOR GIỌNG"       -> "NARRATOR"
    """
    parts = re.split(r"[\s\-–—]+", tag, maxsplit=1)
    return parts[0] if parts and parts[0] else tag


def canonical_voice_role(raw_tag: str) -> Optional[str]:
    """
    Nhận vào 1 raw tag (bên trong [...]), trả về role canonical:
        "narrator" | "female" | "male" | None
    """
    base = extract_base_token(raw_tag).upper()
    return VOICE_BASE_TAGS.get(base)


def is_voice_tag(raw_tag: str) -> bool:
    """Trả về True nếu raw_tag là 1 trong các voice tag hợp lệ."""
    return canonical_voice_role(raw_tag) is not None


def is_technical_tag(raw_tag: str) -> bool:
    """
    Trả về True nếu raw_tag là 1 trong các tag kỹ thuật được support
    (BGM, BGM_DB, SFX, RATE, PAUSE...).

    Rule cố ý chặt hơn so với startswith thuần:
    - chấp nhận TAG
    - chấp nhận TAG=...
    - không chấp nhận legacy lookalike như BGMVOL=...
    """
    up = raw_tag.strip().upper()
    base = extract_base_token(up)
    return any(base == prefix or up.startswith(prefix + "=") for prefix in TECHNICAL_TAG_PREFIXES)




def is_legacy_unsupported_tag(raw_tag: str) -> bool:
    """Trả về True nếu raw_tag thuộc nhóm legacy semantics đã bị loại bỏ."""
    up = raw_tag.strip().upper()
    base = extract_base_token(up)
    return any(base == legacy or up.startswith(legacy + "=") for legacy in LEGACY_UNSUPPORTED_TAGS)

def detect_zone_from_comment(comment_line: str) -> Optional[str]:
    """
    Nhận một dòng comment (đã bỏ dấu // ở đầu), trả về id zone canonical nếu match,
    ngược lại trả về None.
    """
    up = comment_line.strip().upper()
    for zone_id, keywords in ZONE_KEYWORDS.items():
        for kw in keywords:
            if kw in up:
                return zone_id
    return None


# Canonical authoring item shape used before rendering to plain engine script.
CANONICAL_SCRIPT_ITEM_KEYS: Tuple[str, ...] = ("zone", "environment", "voice", "speed", "lang", "text")
DEFAULT_SCRIPT_VOICE = "NARRATOR"
DEFAULT_SCRIPT_SPEED = "NORMAL"
DEFAULT_SCRIPT_LANG = "VI"
ALLOWED_SCRIPT_ZONES: Tuple[str, ...] = (
    "LỜI CHÀO",
    "MỞ TRUYỆN",
    "GIỚI THIỆU",
    "TRIỂN KHAI",
    "CAO TRÀO",
    "HẠ MÀN",
    "KẾT TRUYỆN",
    "TẠM BIỆT",
)
SCRIPT_ZONE_ALIASES: Dict[str, str] = {
    "LỜI CHÀO": "LỜI CHÀO",
    "LOI CHAO": "LỜI CHÀO",
    "GREETING": "LỜI CHÀO",
    "MỞ TRUYỆN": "MỞ TRUYỆN",
    "MO TRUYEN": "MỞ TRUYỆN",
    "MỞ ĐẦU": "MỞ TRUYỆN",
    "MO DAU": "MỞ TRUYỆN",
    "OPENING": "MỞ TRUYỆN",
    "INTRO": "MỞ TRUYỆN",
    "GIỚI THIỆU": "GIỚI THIỆU",
    "GIOI THIEU": "GIỚI THIỆU",
    "INTRODUCTION": "GIỚI THIỆU",
    "TRIỂN KHAI": "TRIỂN KHAI",
    "TRIEN KHAI": "TRIỂN KHAI",
    "DEVELOPMENT": "TRIỂN KHAI",
    "CAO TRÀO": "CAO TRÀO",
    "CAO TRAO": "CAO TRÀO",
    "CLIMAX": "CAO TRÀO",
    "HẠ MÀN": "HẠ MÀN",
    "HA MAN": "HẠ MÀN",
    "FALLING": "HẠ MÀN",
    "KẾT TRUYỆN": "KẾT TRUYỆN",
    "KET TRUYEN": "KẾT TRUYỆN",
    "ENDING": "KẾT TRUYỆN",
    "TẠM BIỆT": "TẠM BIỆT",
    "TAM BIET": "TẠM BIỆT",
    "FAREWELL": "TẠM BIỆT",
}
ALLOWED_SCRIPT_VOICES: Tuple[str, ...] = ("NARRATOR", "MALE", "FEMALE")
ALLOWED_SCRIPT_SPEEDS: Tuple[str, ...] = ("SLOW", "NORMAL", "FAST")
ALLOWED_SCRIPT_LANGS: Tuple[str, ...] = ("VI", "EN")
OUTLINE_KEYS: Tuple[str, ...] = (
    "greeting",
    "opening",
    "introduction",
    "development",
    "climax",
    "falling",
    "ending",
    "farewell",
)
OUTLINE_KEY_ALIASES: Dict[str, str] = {
    "GREETING": "greeting",
    "LỜI CHÀO": "greeting",
    "LOI CHAO": "greeting",
    "OPENING": "opening",
    "INTRO": "opening",
    "MỞ TRUYỆN": "opening",
    "MO TRUYEN": "opening",
    "MỞ ĐẦU": "opening",
    "MO DAU": "opening",
    "INTRODUCTION": "introduction",
    "GIỚI THIỆU": "introduction",
    "GIOI THIEU": "introduction",
    "DEVELOPMENT": "development",
    "TRIỂN KHAI": "development",
    "TRIEN KHAI": "development",
    "CLIMAX": "climax",
    "CAO TRÀO": "climax",
    "CAO TRAO": "climax",
    "FALLING": "falling",
    "HẠ MÀN": "falling",
    "HA MAN": "falling",
    "ENDING": "ending",
    "KẾT TRUYỆN": "ending",
    "KET TRUYEN": "ending",
    "FAREWELL": "farewell",
    "TẠM BIỆT": "farewell",
    "TAM BIET": "farewell",
}
REQUIRED_META_KEYS: Tuple[str, ...] = (
    "title",
    "series",
    "episode",
    "author",
    "channel",
    "target",
    "length_min",
    "length_max",
    "language",
    "genre",
    "audience",
    "tone",
    "tags",
)


OPTIONAL_ROOT_KEYS: Tuple[str, ...] = (
    "_auto_repair_log",
)

SQUARE_BRACKET_TEXT_RE = re.compile(r"[\[\]]")
SENTENCE_END_RE = re.compile(r"(?<!\.)[.!?…](?![\dA-Za-z])")
ABBREVIATION_TAIL_RE = re.compile(r"(?:^|\s)(?:[A-Za-z]\.){2,}$")


def _looks_like_single_sentence(text: str) -> bool:
    """Heuristic check that `text` contains exactly one spoken sentence.

    Accepts a single trailing sentence terminator or no terminator at all.
    Tries to avoid false positives for:
    - ellipsis / repeated dots
    - common dotted abbreviations like U.S.A.
    - decimal numbers like 3.14
    """
    s = (text or "").strip()
    if not s:
        return False

    matches = list(SENTENCE_END_RE.finditer(s))
    if not matches:
        return True

    # Ignore a final punctuation mark; any earlier boundary suggests >1 sentence.
    last = matches[-1]
    inner = matches[:-1]
    if inner:
        return False

    tail = s[:last.end()].rstrip()
    if ABBREVIATION_TAIL_RE.search(tail):
        return True

    return last.end() == len(s)


def _normalize_zone_label(zone: object) -> str:
    s = "" if zone is None else str(zone).strip()
    return s.upper()


def canonical_script_zone_label(zone: object) -> str:
    """Normalize English/Vietnamese script zone labels to the canonical Vietnamese form."""
    raw = _normalize_zone_label(zone)
    return SCRIPT_ZONE_ALIASES.get(raw, raw)


def normalize_outline_key(key: object) -> str:
    """Normalize English/Vietnamese outline keys to the canonical English form."""
    s = "" if key is None else str(key).strip()
    return OUTLINE_KEY_ALIASES.get(s.upper(), s)


def build_meta_header(meta: dict) -> str:
    """Render plain-script header from canonical meta."""
    lines: List[str] = ["# FORMAT: AUDIO_STORY_PLAIN"]

    def add(label: str, key: str) -> None:
        value = meta.get(key)
        if value is not None and str(value).strip() != "":
            lines.append(f"# {label}: {value}")

    add("TITLE", "title")
    add("SERIES", "series")
    add("EPISODE", "episode")
    add("AUTHOR", "author")
    add("CHANNEL", "channel")
    add("TARGET", "target")

    length_min = meta.get("length_min")
    length_max = meta.get("length_max")
    if length_min or length_max:
        if length_min and length_max:
            length_str = f"{length_min}–{length_max} phút"
        elif length_min:
            length_str = f"{length_min}+ phút"
        else:
            length_str = f"≤ {length_max} phút"
        lines.append(f"# LENGTH: {length_str}")

    lines.append("")
    lines.append("SCRIPT:")
    lines.append("")
    return "\n".join(lines)


def render_plain_script(authoring: dict) -> str:
    """Render full plain engine script from canonical authoring JSON."""
    meta = authoring.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    return build_meta_header(meta) + render_canonical_script_items(authoring.get("script", []))


def _validate_auto_repair_log(value: Any) -> List[str]:
    """
    _auto_repair_log là field root tùy chọn để lưu vết auto-repair.
    Chấp nhận list[object]. Không ép cứng schema chi tiết để tránh
    làm gãy backward-compat khi format log thay đổi nhẹ theo thời gian.
    """
    errors: List[str] = []

    if value is None:
        return errors

    if not isinstance(value, list):
        return ["_auto_repair_log phải là array nếu có."]
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            errors.append(f"_auto_repair_log[{idx}] phải là object.")
    return errors


def validate_canonical_authoring(data: Any) -> List[str]:
    """Validate canonical authoring JSON used by the repo.

    Canonical contract:
    - root object with keys: meta, outline, script
    - optional root metadata keys: _auto_repair_log
    - script is an array of flat canonical items
    - `script` must be an array of canonical items
    - zones must cover all 8 canonical zones in order and never go backward
    """
    errors: List[str] = []

    if not isinstance(data, dict):
        return ["Root JSON phải là object."]

    allowed_root = {"meta", "outline", "script", *OPTIONAL_ROOT_KEYS}
    extra_root = sorted(set(data.keys()) - allowed_root)
    if extra_root:
        errors.append(
            f"Root JSON có field không hợp lệ: {extra_root}. "
            "Chỉ cho phép meta/outline/script và _auto_repair_log."
        )

    if "_auto_repair_log" in data:
        errors.extend(_validate_auto_repair_log(data.get("_auto_repair_log")))

    meta = data.get("meta")
    if not isinstance(meta, dict):
        errors.append("meta phải là object.")
    else:
        extra_meta = sorted(set(meta.keys()) - set(REQUIRED_META_KEYS))
        if extra_meta:
            errors.append(f"meta có field không hợp lệ: {extra_meta}.")
        missing_meta = [k for k in REQUIRED_META_KEYS if k not in meta]
        if missing_meta:
            errors.append(f"meta thiếu field bắt buộc: {missing_meta}.")
        for k in REQUIRED_META_KEYS:
            if k not in meta:
                continue
            v = meta.get(k)
            if k in ("length_min", "length_max"):
                if not isinstance(v, int):
                    errors.append(f"meta.{k} phải là integer.")
            elif k == "tags":
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    errors.append("meta.tags phải là array[string].")
            else:
                if not isinstance(v, str):
                    errors.append(f"meta.{k} phải là string.")
                elif k not in {"series", "episode"} and not v.strip():
                    errors.append(f"meta.{k} phải là string không rỗng.")
        lang = str(meta.get("language", "")).strip().lower()
        if lang and lang not in {"vi", "en"}:
            errors.append("meta.language chỉ được là 'vi' hoặc 'en'.")

    outline = data.get("outline")
    if not isinstance(outline, dict):
        errors.append("outline phải là object gồm đúng 8 zone summary.")
    else:
        normalized_outline = {normalize_outline_key(k): v for k, v in outline.items()}
        extra_outline = sorted(set(normalized_outline.keys()) - set(OUTLINE_KEYS))
        if extra_outline:
            errors.append(f"outline có field không hợp lệ: {extra_outline}.")
        outline_keys = [normalize_outline_key(k) for k in outline.keys()]
        if tuple(outline_keys) != OUTLINE_KEYS:
            errors.append(f"outline phải có đúng 8 key theo thứ tự: {list(OUTLINE_KEYS)}.")
        for key in OUTLINE_KEYS:
            value = normalized_outline.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"outline.{key} phải là string không rỗng.")

    if "script" not in data:
        errors.append("Thiếu field script.")
        return errors

    script = data.get("script")
    if isinstance(script, str):
        errors.append("script phải là array canonical, không được là string.")
        return errors
    if not isinstance(script, list):
        errors.append("script phải là array canonical.")
        return errors
    if not script:
        errors.append("script phải có ít nhất 1 item.")
        return errors

    zones_seen: List[str] = []
    zone_idx = 0
    last_zone_pos = -1

    for idx, item in enumerate(script, start=1):
        if not isinstance(item, dict):
            errors.append(f"script[{idx}] phải là object.")
            continue
        extra_keys = sorted(set(item.keys()) - set(CANONICAL_SCRIPT_ITEM_KEYS))
        missing_keys = [k for k in CANONICAL_SCRIPT_ITEM_KEYS if k not in item]
        if missing_keys:
            errors.append(f"script[{idx}] thiếu field bắt buộc: {missing_keys}.")
        if extra_keys:
            errors.append(f"script[{idx}] có field không hợp lệ: {extra_keys}.")

        zone = canonical_script_zone_label(item.get("zone"))
        environment = "" if item.get("environment") is None else str(item.get("environment")).strip()
        voice = _normalize_render_value(item.get("voice"), DEFAULT_SCRIPT_VOICE)
        speed = _normalize_render_value(item.get("speed"), DEFAULT_SCRIPT_SPEED)
        lang = _normalize_render_value(item.get("lang"), DEFAULT_SCRIPT_LANG)
        text = "" if item.get("text") is None else str(item.get("text")).strip()

        if zone not in ALLOWED_SCRIPT_ZONES:
            errors.append(f"script[{idx}].zone không hợp lệ: {zone!r}.")
        else:
            zones_seen.append(zone)
            try:
                current_pos = ALLOWED_SCRIPT_ZONES.index(zone)
            except ValueError:
                current_pos = -1
            if current_pos >= 0:
                if current_pos < last_zone_pos:
                    errors.append(f"script[{idx}].zone đi lùi thứ tự: {zone}.")
                last_zone_pos = max(last_zone_pos, current_pos)
                while zone_idx < len(ALLOWED_SCRIPT_ZONES) and ALLOWED_SCRIPT_ZONES[zone_idx] == zone:
                    zone_idx += 1

        if item.get("environment") is None:
            errors.append(f"script[{idx}].environment không được thiếu.")
        elif not isinstance(item.get("environment"), str):
            errors.append(f"script[{idx}].environment phải là string.")
        if voice not in ALLOWED_SCRIPT_VOICES:
            errors.append(f"script[{idx}].voice không hợp lệ: {voice!r}.")
        if speed not in ALLOWED_SCRIPT_SPEEDS:
            errors.append(f"script[{idx}].speed không hợp lệ: {speed!r}.")
        if lang not in ALLOWED_SCRIPT_LANGS:
            errors.append(f"script[{idx}].lang không hợp lệ: {lang!r}.")
        if not text:
            errors.append(f"script[{idx}].text không được để trống.")
        elif SQUARE_BRACKET_TEXT_RE.search(text):
            errors.append(f"script[{idx}].text không được chứa '[' hoặc ']'.")
        elif not _looks_like_single_sentence(text):
            preview = text if len(text) <= 120 else text[:117] + '...'
            errors.append(f"script[{idx}].text phải chứa đúng 1 câu. text={preview!r}")

    if zones_seen:
        missing_order = [z for z in ALLOWED_SCRIPT_ZONES if z not in zones_seen]
        if missing_order:
            errors.append(f"script phải bao phủ đủ 8 zone canonical: {missing_order}.")
        else:
            first_pos = [zones_seen.index(z) for z in ALLOWED_SCRIPT_ZONES]
            if first_pos != sorted(first_pos):
                errors.append("script phải bao phủ đủ 8 zone theo đúng thứ tự và không được đi ngược.")

    return errors


def _normalize_render_value(value: object, default: str) -> str:
    s = "" if value is None else str(value).strip()
    return s.upper() if s else default


def render_canonical_script_items(script: object) -> str:
    """
    Render canonical authoring `script` (array of flat items) to plain engine-script body.

    Canonical item shape:
        {
          "zone": str,
          "voice": "NARRATOR|MALE|FEMALE" (default NARRATOR),
          "environment": str,
          "speed": "SLOW|NORMAL|FAST"      (default NORMAL),
          "lang":  "VI|EN"                 (default VI),
          "text":  str
        }

    Rules:
    - `script` must be a list.
    - each item must be an object.
    - `zone` and `text` are required and must be non-empty after strip.
    - output is body-only, without metadata header or `SCRIPT:` marker.
    """
    if not isinstance(script, list):
        raise TypeError("JSON phải có field 'script' dạng array canonical.")

    out: List[str] = []
    last_zone: Optional[str] = None

    for idx, item in enumerate(script, start=1):
        if not isinstance(item, dict):
            raise TypeError(f"script[{idx}] phải là object.")

        zone = "" if item.get("zone") is None else str(item.get("zone")).strip()
        text = "" if item.get("text") is None else str(item.get("text")).strip()
        if not zone:
            raise ValueError(f"script[{idx}].zone không được để trống.")
        if not text:
            raise ValueError(f"script[{idx}].text không được để trống.")

        environment = "" if item.get("environment") is None else str(item.get("environment")).strip()
        voice = _normalize_render_value(item.get("voice"), DEFAULT_SCRIPT_VOICE)
        speed = _normalize_render_value(item.get("speed"), DEFAULT_SCRIPT_SPEED)
        lang = _normalize_render_value(item.get("lang"), DEFAULT_SCRIPT_LANG)

        if zone != last_zone:
            if out:
                out.append("")
            out.append(f"// {zone}")
            last_zone = zone

        out.append(f"[{voice}][{speed}][{lang}] {text}")

    return "\n".join(out).rstrip() + "\n"
