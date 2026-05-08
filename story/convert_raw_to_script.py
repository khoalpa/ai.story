#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
convert_raw_to_script.py

Mục tiêu
- Bổ sung tag (voice/speed/lang) cho kịch bản chưa có tag hoặc thiếu tag.
- Đảm bảo file đầu ra phù hợp plain engine script (có dòng SCRIPT:).

Thiết kế (safe defaults)
- Không phá tag đã có.
- Chỉ thêm tag khi thiếu.
- Nếu không có dòng "SCRIPT:" → tự thêm header tối thiểu + "SCRIPT:".
- Nếu gặp các tiêu đề zone dạng "LỜI CHÀO", "MỞ TRUYỆN",... (không có //)
  → chuyển thành comment "// <ZONE>" để engine/validator nhận diện zone.

CLI ví dụ
    # Convert file văn bản thuần sang plain engine script + auto tag
    python convert_raw_to_script.py -i raw_story.txt -o story_tagged.txt

    # Chỉ bổ sung tag cho file đã có SCRIPT:
    python convert_raw_to_script.py -i story.txt -o story_fixed.txt --no-header

    # Ưu tiên giọng mặc định khác
    python convert_raw_to_script.py -i raw.txt -o out.txt --default-voice MALE --default-lang VI

Gợi ý workflow
1) Convert:  python convert_raw_to_script.py -i raw.txt -o story.txt
2) Validate: python validate_script.py -i story.txt
3) Render:   python make_audio_edge_tts.py -i story.txt -o out --bgm bgm_lofi.mp3
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .audio_story_spec import TAG_PATTERN, VOICE_BASE_TAGS, ZONE_KEYWORDS, canonical_voice_role

# ----------------------------
# Helpers: header + detection
# ----------------------------

def build_min_header(title: str = "") -> str:
    """
    Header tối thiểu cho plain engine script.
    """
    lines = ["# FORMAT: AUDIO_STORY_PLAIN"]
    if title.strip():
        lines.append(f"# TITLE: {title.strip()}")
    lines.append("")
    lines.append("SCRIPT:")
    lines.append("")
    return "\n".join(lines)


def has_script_marker(lines: List[str]) -> bool:
    return any(l.strip().upper().startswith("SCRIPT:") for l in lines)


def split_header_and_script(lines: List[str]) -> Tuple[List[str], List[str]]:
    """
    Tách phần header và phần script (sau dòng SCRIPT:).
    Nếu không có SCRIPT: -> ([], lines).
    """
    for idx, raw in enumerate(lines):
        if raw.strip().upper().startswith("SCRIPT:"):
            return lines[: idx + 1], lines[idx + 1 :]
    return [], lines[:]


VI_DIACRITICS = set(
    "ăâđêôơưĂÂĐÊÔƠƯ"
    "áàảãạăắằẳẵặâấầẩẫậ"
    "éèẻẽẹêếềểễệ"
    "íìỉĩị"
    "óòỏõọôốồổỗộơớờởỡợ"
    "úùủũụưứừửữự"
    "ýỳỷỹỵ"
    "ÁÀẢÃẠÉÈẺẼẸÍÌỈĨỊÓÒỎÕỌÚÙỦŨỤÝỲỶỸỴ"
)


def is_english_like(text: str, threshold: float = 0.7) -> bool:
    """
    Heuristic: dòng "giống tiếng Anh" nếu:
    - Không chứa dấu tiếng Việt
    - Tỷ lệ ký tự chữ cái A–Z trên tổng chữ cái >= threshold
    """
    text = text.strip()
    if not text:
        return False
    if any(ch in VI_DIACRITICS for ch in text):
        return False

    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    english_letters = [ch for ch in letters if "A" <= ch.upper() <= "Z"]
    return (len(english_letters) / len(letters)) >= threshold


def normalize_zone_heading(s: str) -> str:
    # Chuẩn hoá bỏ khoảng trắng thừa, bỏ dấu gạch/2 chấm cuối dòng
    s = s.strip()
    s = re.sub(r"[:：\-–—\s]+$", "", s).strip()
    return s


def is_zone_heading(line: str) -> Optional[str]:
    """
    Nếu line là tiêu đề zone (không có //) thì trả về bản gốc phù hợp để in vào comment.
    """
    cleaned = normalize_zone_heading(line)
    if not cleaned:
        return None

    upper = cleaned.upper()
    for _zone_id, keywords in ZONE_KEYWORDS.items():
        for kw in keywords:
            if upper == kw:
                # trả về chính keyword tiếng Việt (ưu tiên cái user gõ)
                return cleaned
    return None


def extract_tags(line: str) -> List[str]:
    return [t.strip() for t in TAG_PATTERN.findall(line)]


def has_any_voice_tag(tags: List[str]) -> bool:
    for t in tags:
        if canonical_voice_role(t) is not None:
            return True
    return False


def has_any_speed_tag(tags: List[str]) -> bool:
    for t in tags:
        up = t.strip().upper()
        base = up.split("=", 1)[0].strip()
        if base in ("SLOW", "FAST", "NORMAL") or base.startswith("RATE"):
            return True
    return False


def has_any_lang_tag(tags: List[str]) -> bool:
    for t in tags:
        up = t.strip().upper()
        if up == "VI" or up == "EN":
            return True
    return False


# ----------------------------
# Speaker inference
# ----------------------------

@dataclass
class SpeakerConfig:
    """
    Mapping đơn giản: tên nhân vật -> voice role.
    """
    name_to_voice: Dict[str, str]

    @staticmethod
    def default() -> "SpeakerConfig":
        # Có thể mở rộng tuỳ dự án
        return SpeakerConfig(
            name_to_voice={
                "minh": "male",
                "lan": "female",
                "anh": "male",
                "chị": "female",
                "em": "female",  # heuristic yếu, nhưng hợp chuyện tình cảm
                "cô": "female",
                "cậu": "male",
            }
        )


SPEAKER_PREFIX_RE = re.compile(r"^\s*([A-Za-zÀ-ỹ0-9_\- ]{1,30})\s*:\s*(.+)$")


def infer_voice_from_prefix(text: str, speaker_cfg: SpeakerConfig) -> Optional[str]:
    """
    Nếu dòng có dạng "Lan: ..." -> map sang female/male theo config.
    Trả về role canonical ("narrator"|"female"|"male") hoặc None.
    """
    m = SPEAKER_PREFIX_RE.match(text)
    if not m:
        return None
    speaker = (m.group(1) or "").strip().lower()
    return speaker_cfg.name_to_voice.get(speaker)


def strip_speaker_prefix(text: str) -> str:
    m = SPEAKER_PREFIX_RE.match(text)
    if not m:
        return text
    return (m.group(2) or "").strip()


# ----------------------------
# Core conversion
# ----------------------------

def canonical_voice_tag(role: str) -> str:
    """
    Trả về tag giọng canonical trong DSL: [NARRATOR]/[FEMALE]/[MALE].
    """
    role = (role or "").strip().lower()
    if role == "female":
        return "[FEMALE]"
    if role == "male":
        return "[MALE]"
    return "[NARRATOR]"


def normalize_default_voice(v: str) -> str:
    up = (v or "").strip().upper()
    if up in VOICE_BASE_TAGS:
        return VOICE_BASE_TAGS[up]  # narrator/female/male
    # cho phép user truyền narrator/female/male
    low = (v or "").strip().lower()
    if low in ("narrator", "female", "male"):
        return low
    return "narrator"


def normalize_default_speed(s: str) -> str:
    up = (s or "").strip().upper()
    if up in ("SLOW", "FAST", "NORMAL"):
        return up
    return "NORMAL"


def normalize_default_lang(s: str) -> str:
    up = (s or "").strip().upper()
    if up in ("VI", "EN"):
        return up
    return "VI"


def ensure_tags_for_line(
    line: str,
    default_voice_role: str,
    default_speed: str,
    default_lang: str,
    speaker_cfg: SpeakerConfig,
    auto_en: bool,
    strip_prefix: bool,
) -> str:
    """
    Thêm tag thiếu cho 1 dòng thoại (không phải comment).
    Quy tắc:
    - Nếu đã có voice tag thì giữ nguyên.
    - Nếu chưa có voice tag:
        + thử infer từ "Name: ..." (nếu có)
        + nếu không infer được → dùng default_voice_role
    - Nếu chưa có speed tag → thêm [NORMAL] (hoặc default_speed)
    - Nếu chưa có lang tag → thêm [VI] hoặc [EN] (auto_en nếu bật)
    """
    original = line.rstrip("\n")
    stripped = original.strip()
    if not stripped:
        return original

    # Không đụng comment line
    if stripped.startswith("//"):
        return original

    # Nếu dòng chỉ là tag kỹ thuật (vd: [PAUSE 1s]) vẫn nên có tag? -> không bắt buộc.
    # Ở đây: nếu dòng KHÔNG có text sau khi bỏ tags, thì giữ nguyên.
    tags = extract_tags(stripped)
    text_wo_tags = TAG_PATTERN.sub("", stripped).strip()
    if not text_wo_tags and tags:
        return original

    # Infer voice via prefix "Lan: ..."
    inferred_role = infer_voice_from_prefix(text_wo_tags, speaker_cfg)

    if strip_prefix and inferred_role is not None:
        # bỏ "Lan:" khỏi text để tránh đọc "Lan"
        new_text = strip_speaker_prefix(text_wo_tags)
        # giữ lại các tags đã có (kỹ thuật)
        stripped = TAG_PATTERN.sub("", stripped).strip()  # remove tags entirely then re-add later
        # rebuild line later from tags + new_text; but we still need original tags
        # We'll do: keep original line but replace text part. easiest: replace text_wo_tags segment.
        # Here do a simple rebuild: tags_text + new_text
        # We'll only preserve the tags that already exist in line (excluding voice/speed/lang, which we manage).
        technical_tags = []
        for t in tags:
            up = t.upper()
            base = up.split("=", 1)[0].strip()
            if base in ("VI", "EN", "SLOW", "FAST", "NORMAL") or base.startswith("RATE"):
                continue
            if base in VOICE_BASE_TAGS:
                continue
            technical_tags.append(f"[{t}]")
        stripped = "".join(technical_tags) + " " + new_text
        tags = extract_tags(stripped)  # recompute after rebuild

    # Re-extract after potential rebuild
    tags = extract_tags(stripped)

    need_voice = not has_any_voice_tag(tags)
    need_speed = not has_any_speed_tag(tags)
    need_lang = not has_any_lang_tag(tags)

    prefix = ""

    if need_voice:
        role = inferred_role or default_voice_role
        prefix += canonical_voice_tag(role)

    if need_speed:
        prefix += f"[{default_speed}]"

    if need_lang:
        lang = default_lang
        if auto_en:
            # auto EN only if no existing lang tag
            text_clean = TAG_PATTERN.sub("", stripped).strip()
            if is_english_like(text_clean):
                lang = "EN"
        prefix += f"[{lang}]"

    if prefix:
        # đảm bảo prefix đứng trước mọi tag kỹ thuật đang có (BGM, PAUSE...)
        return prefix + " " + stripped
    return original


def convert_text(
    in_text: str,
    *,
    add_header_if_missing: bool,
    title_hint: str,
    default_voice_role: str,
    default_speed: str,
    default_lang: str,
    auto_en: bool,
    speaker_cfg: SpeakerConfig,
    strip_prefix: bool,
) -> str:
    lines = in_text.splitlines()
    header_lines, script_lines = split_header_and_script(lines)

    out_lines: List[str] = []

    if header_lines:
        # giữ nguyên header có sẵn
        out_lines.extend(header_lines)
    else:
        if add_header_if_missing:
            out_lines.extend(build_min_header(title_hint).splitlines())
        else:
            # nếu không add header, vẫn phải có SCRIPT: để qua validator
            out_lines.append("SCRIPT:")
            out_lines.append("")

        script_lines = lines[:]  # toàn file coi như script

    # Convert script lines
    for raw in script_lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if not stripped:
            out_lines.append(line)
            continue

        # giữ nguyên metadata lines bắt đầu "#"
        if stripped.startswith("#"):
            out_lines.append(line)
            continue

        # Comment lines
        if stripped.startswith("//"):
            out_lines.append(line)
            continue

        # Zone headings (dòng thuần "LỜI CHÀO", ...)
        zh = is_zone_heading(stripped)
        if zh is not None:
            out_lines.append(f"// {zh}")
            continue

        # Speech / narrative line
        out_lines.append(
            ensure_tags_for_line(
                line,
                default_voice_role=default_voice_role,
                default_speed=default_speed,
                default_lang=default_lang,
                speaker_cfg=speaker_cfg,
                auto_en=auto_en,
                strip_prefix=strip_prefix,
            )
        )

    # đảm bảo newline cuối file
    return "\n".join(out_lines).rstrip() + "\n"


# ----------------------------
# CLI
# ----------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bổ sung tag cho kịch bản chưa có tag (plain engine script Audio Story).")
    p.add_argument("-i", "--input", required=True, help="Input text/script file (có thể chưa có tag).")
    p.add_argument("-o", "--output", required=True, help="Output file (đã được bổ sung tag).")

    p.add_argument("--title", default="", help="TITLE hint (nếu input chưa có header).")

    p.add_argument("--no-header", action="store_true", help="Không tự thêm header nếu input thiếu SCRIPT:.")
    p.add_argument("--default-voice", default="NARRATOR", help="NARRATOR | FEMALE | MALE (mặc định: NARRATOR).")
    p.add_argument("--default-speed", default="NORMAL", help="SLOW | NORMAL | FAST (mặc định: NORMAL).")
    p.add_argument("--default-lang", default="VI", help="VI | EN (mặc định: VI).")
    p.add_argument("--auto-en", action="store_true", help="Tự thêm [EN] cho dòng giống tiếng Anh (khi thiếu [VI]/[EN]).")

    p.add_argument(
        "--strip-speaker-prefix",
        action="store_true",
        help="Nếu dòng có dạng 'Lan: ...'/'Minh: ...' thì bỏ phần 'Lan:' để tránh TTS đọc tên.",
    )

    args = p.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.is_file():
        raise SystemExit(f"Không tìm thấy input: {in_path}")

    text = in_path.read_text(encoding="utf-8")

    speaker_cfg = SpeakerConfig.default()

    out_text = convert_text(
        text,
        add_header_if_missing=(not args.no_header),
        title_hint=args.title,
        default_voice_role=normalize_default_voice(args.default_voice),
        default_speed=normalize_default_speed(args.default_speed),
        default_lang=normalize_default_lang(args.default_lang),
        auto_en=args.auto_en,
        speaker_cfg=speaker_cfg,
        strip_prefix=args.strip_speaker_prefix,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding="utf-8")

    print(f"✅ Đã tạo: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

