#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Module validate_plain_script.py

Dùng để KIỂM TRA TỰ ĐỘNG file kịch bản truyện audio
(trước khi đưa vào make_audio_edge_tts.py).

Chức năng:
- Tìm phần SCRIPT: trong file .txt (bỏ qua mọi dòng phía trên, ví dụ metadata #...)
- Kiểm tra 8 zone: LỜI CHÀO / MỞ TRUYỆN / GIỚI THIỆU / TRIỂN KHAI / CAO TRÀO / HẠ MÀN / KẾT TRUYỆN / TẠM BIỆT
- Kiểm tra từng dòng thoại:
    + Có tag giọng [NARRATOR]/[MALE]/[FEMALE] không?
    + Có tag lạ không?
    + Câu quá dài, khó đọc?
    + ...
- Xuất báo cáo errors/warnings + thống kê.

Cách dùng (CLI):
    python validate_plain_script.py -i story.txt
    python validate_plain_script.py -i story.txt --json
"""

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Sequence

from audio.cli_utils import UsedFilesTracker, setup_stdio

from audio.audio_story_spec import (
    TAG_PATTERN,
    VOICE_BASE_TAGS,
    TECHNICAL_TAG_PREFIXES,
    ZONE_KEYWORDS,
    extract_base_token,
    is_legacy_unsupported_tag,
)


###############################################################################
# DATA CLASSES
###############################################################################

@dataclass
class LineIssue:
    line_no: int
    line_text: str
    issue_type: str   # "error" | "warning"
    message: str


@dataclass
class ScriptStats:
    total_lines: int = 0
    script_lines: int = 0
    comment_lines: int = 0
    empty_lines: int = 0

    voice_lines: int = 0
    voice_narrator: int = 0
    voice_female: int = 0
    voice_male: int = 0
    no_voice_tag_lines: int = 0

    unknown_tag_count: int = 0
    unknown_tags: Dict[str, int] = None

    zones_found: Dict[str, bool] = None


@dataclass
class ValidationResult:
    ok: bool
    errors: List[LineIssue]
    warnings: List[LineIssue]
    stats: ScriptStats


###############################################################################
# HÀM TIỆN ÍCH
###############################################################################

def load_text_file(path: Path) -> List[str]:
    """Đọc file text và trả về list dòng (không kèm newline)."""
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read().splitlines()


def looks_like_body_only_script(lines: List[str]) -> bool:
    """
    Nhận diện trường hợp người dùng chỉ dán phần body script, không có header/SCRIPT:.
    Ví dụ:
        // LỜI CHÀO
        [NARRATOR][VI] Xin chào.
    """
    non_empty = [line.strip() for line in lines if line.strip()]
    if not non_empty:
        return False

    signal_count = 0
    for line in non_empty[:12]:
        if line.startswith("//") or line.startswith("["):
            signal_count += 1
            continue
        if TAG_PATTERN.search(line):
            signal_count += 1
            continue

    return signal_count >= 1


def detect_body_only_script(lines: List[str]) -> bool:
    """
    Backward-compatible alias cho GUI helpers đang import tên cũ.
    """
    return looks_like_body_only_script(lines)


def detect_script_block(lines: List[str]) -> int:
    """
    Tìm dòng "SCRIPT:" (không phân biệt hoa thường, cho phép khoảng trắng).
    Trả về index (0-based) của dòng SCRIPT, hoặc -1 nếu không thấy.
    """
    for idx, raw in enumerate(lines):
        if raw.strip().upper().startswith("SCRIPT:"):
            return idx
    return -1


def classify_zone_from_comment(comment_text: str) -> Optional[str]:
    """
    Nhận diện zone từ câu comment (dòng bắt đầu bằng //).
    Trả về: "greeting" | "opening" | "introduction" | "development" | "climax" | "falling" | "ending" | "farewell" | None
    """
    upper = comment_text.upper()
    for zone, keywords in ZONE_KEYWORDS.items():
        for kw in keywords:
            if kw in upper:
                return zone
    return None


###############################################################################
# CORE VALIDATION LOGIC
###############################################################################

def validate_script(lines: List[str]) -> ValidationResult:
    """
    Thực hiện toàn bộ logic validate script:
        - Kiểm tra tồn tại SCRIPT:
        - Duyệt từng dòng, bắt lỗi / cảnh báo
        - Ghi nhận thống kê (stats)
    """
    stats = ScriptStats(
        unknown_tags={},
        zones_found={zone: False for zone in ZONE_KEYWORDS.keys()},
    )
    errors: List[LineIssue] = []
    warnings: List[LineIssue] = []

    stats.total_lines = len(lines)

    # 1) Tìm block SCRIPT
    script_idx = detect_script_block(lines)
    if script_idx < 0:
        if looks_like_body_only_script(lines):
            script_lines = lines
            warnings.append(
                LineIssue(
                    line_no=0,
                    line_text="",
                    issue_type="warning",
                    message=(
                        "Không thấy dòng 'SCRIPT:' nhưng file có vẻ là body-only script. "
                        "Validator sẽ tạm coi toàn bộ file là nội dung kịch bản. "
                        "Nên thêm dòng 'SCRIPT:' để chuẩn hóa định dạng."
                    ),
                )
            )
        else:
            errors.append(
                LineIssue(
                    line_no=0,
                    line_text="",
                    issue_type="error",
                    message=(
                        "Không tìm thấy dòng 'SCRIPT:' trong file. "
                        "Hãy thêm dòng 'SCRIPT:' để đánh dấu phần kịch bản."
                    ),
                )
            )
            return ValidationResult(ok=False, errors=errors, warnings=warnings, stats=stats)
    else:
        # 2) Lấy phần sau SCRIPT:
        script_lines = lines[script_idx + 1 :]
    if not script_lines:
        errors.append(
            LineIssue(
                line_no=script_idx + 1,
                line_text="",
                issue_type="error",
                message="Sau dòng 'SCRIPT:' không có nội dung nào.",
            )
        )
        return ValidationResult(ok=False, errors=errors, warnings=warnings, stats=stats)

    # 3) Duyệt từng dòng script
    for offset, raw in enumerate(script_lines, start=script_idx + 2):
        line = raw.rstrip("\n")
        stripped = line.strip()

        if not stripped:
            stats.empty_lines += 1
            continue

        # Comment line?
        if stripped.startswith("//"):
            stats.comment_lines += 1
            zone = classify_zone_from_comment(stripped)
            if zone:
                stats.zones_found[zone] = True
            continue

        # Nội dung script thực sự
        stats.script_lines += 1

        # Tách tag
        tags = TAG_PATTERN.findall(line)
        has_voice_tag = False
        voice_this_line: Optional[str] = None
        unknown_tags_local: List[str] = []

        for t in tags:
            raw_tag = t.strip()
            upper = raw_tag.upper()
            base = extract_base_token(upper)

            # Voice tag?
            if base in VOICE_BASE_TAGS:
                has_voice_tag = True
                voice_code = VOICE_BASE_TAGS[base]
                voice_this_line = voice_code
                continue

            # Legacy tag bị loại bỏ hẳn
            if is_legacy_unsupported_tag(raw_tag):
                errors.append(
                    LineIssue(
                        line_no=offset,
                        line_text=line,
                        issue_type="error",
                        message=(
                            f"Legacy tag không còn được hỗ trợ: [{raw_tag}]. "
                            "Hãy dùng [BGM_DB=...] cho mức âm lượng BGM theo dB và xóa semantics cũ như BGMVOL/volume."
                        ),
                    )
                )
                continue

            # Tag kỹ thuật?
            is_technical = False
            for prefix in TECHNICAL_TAG_PREFIXES:
                if base == prefix or upper.startswith(prefix + "="):
                    is_technical = True
                    break

            if not is_technical:
                # Tag lạ
                unknown_tags_local.append(raw_tag)

        # Thống kê voice
        if has_voice_tag:
            stats.voice_lines += 1
            if voice_this_line == "narrator":
                stats.voice_narrator += 1
            elif voice_this_line == "female":
                stats.voice_female += 1
            elif voice_this_line == "male":
                stats.voice_male += 1
        else:
            stats.no_voice_tag_lines += 1
            warnings.append(
                LineIssue(
                    line_no=offset,
                    line_text=line,
                    issue_type="warning",
                    message=(
                        "Dòng thoại không có tag giọng nào ([NARRATOR]/[MALE]/[FEMALE]...). "
                        "Nên thêm tag giọng để tool chọn voice chính xác."
                    ),
                )
            )

        # Ghi nhận unknown_tags
        for ut in unknown_tags_local:
            stats.unknown_tag_count += 1
            stats.unknown_tags[ut] = stats.unknown_tags.get(ut, 0) + 1
            warnings.append(
                LineIssue(
                    line_no=offset,
                    line_text=line,
                    issue_type="warning",
                    message=(
                        f"Tag không nhận diện được: [{ut}]. "
                        "Kiểm tra lại chính tả hoặc quy ước tag."
                    ),
                )
            )

        # Kiểm tra câu quá dài, ít dấu câu
        # (Heuristic: > 300 char & không có .?!…)
        pure_text = TAG_PATTERN.sub("", line).strip()
        if len(pure_text) > 300 and not re.search(r"[\.?!…]", pure_text):
            warnings.append(
                LineIssue(
                    line_no=offset,
                    line_text=line,
                    issue_type="warning",
                    message=(
                        "Dòng thoại rất dài (>300 ký tự) và gần như không có dấu kết câu. "
                        "Nên cân nhắc chia nhỏ thành nhiều câu để nghe dễ hơn."
                    ),
                )
            )

    # 4) Sau khi quét xong, kiểm tra zone
    for zone, found in stats.zones_found.items():
        if not found:
            zone_label = {
                "greeting": "LỜI CHÀO",
                "opening": "MỞ TRUYỆN",
                "introduction": "GIỚI THIỆU",
                "development": "TRIỂN KHAI",
                "climax": "CAO TRÀO",
                "falling": "HẠ MÀN",
                "ending": "KẾT TRUYỆN",
                "farewell": "TẠM BIỆT",
            }[zone]
            warnings.append(
                LineIssue(
                    line_no=0,
                    line_text="",
                    issue_type="warning",
                    message=(
                        f"Không tìm thấy comment zone cho {zone_label} trong phần SCRIPT "
                        "(vd: // {zone_label}). "
                        "Tool vẫn chạy được nhưng auto BGM theo zone có thể không như mong muốn."
                    ),
                )
            )

    # Quyết định ok?
    ok = len(errors) == 0

    return ValidationResult(ok=ok, errors=errors, warnings=warnings, stats=stats)


###############################################################################
# XUẤT KẾT QUẢ
###############################################################################

def result_to_dict(res: ValidationResult) -> Dict[str, Any]:
    """Chuyển ValidationResult sang dict (phù hợp để dump JSON)."""
    return {
        "ok": res.ok,
        "errors": [
            {
                "line_no": e.line_no,
                "issue_type": e.issue_type,
                "message": e.message,
                "line_text": e.line_text,
            }
            for e in res.errors
        ],
        "warnings": [
            {
                "line_no": w.line_no,
                "issue_type": w.issue_type,
                "message": w.message,
                "line_text": w.line_text,
            }
            for w in res.warnings
        ],
        "stats": {
            "total_lines": res.stats.total_lines,
            "script_lines": res.stats.script_lines,
            "comment_lines": res.stats.comment_lines,
            "empty_lines": res.stats.empty_lines,
            "voice_lines": res.stats.voice_lines,
            "voice_narrator": res.stats.voice_narrator,
            "voice_female": res.stats.voice_female,
            "voice_male": res.stats.voice_male,
            "no_voice_tag_lines": res.stats.no_voice_tag_lines,
            "unknown_tag_count": res.stats.unknown_tag_count,
            "unknown_tags": res.stats.unknown_tags,
            "zones_found": res.stats.zones_found,
        },
    }


def print_human_readable(res: ValidationResult, file_path: Path) -> None:
    """In báo cáo validate dạng dễ đọc cho người dùng CLI."""
    print("=" * 60)
    print(f"VALIDATE SCRIPT: {file_path}")
    print("=" * 60)
    print(f"- Tổng số dòng           : {res.stats.total_lines}")
    print(f"- Số dòng script (thoại) : {res.stats.script_lines}")
    print(f"- Số dòng comment        : {res.stats.comment_lines}")
    print(f"- Số dòng trống          : {res.stats.empty_lines}")
    print()
    print(f"- Số dòng có voice tag   : {res.stats.voice_lines}")
    print(f"    + Narrator           : {res.stats.voice_narrator}")
    print(f"    + Female             : {res.stats.voice_female}")
    print(f"    + Male               : {res.stats.voice_male}")
    print(f"- Số dòng không có voice : {res.stats.no_voice_tag_lines}")
    print()
    print("- Zone tìm thấy:")
    for zone, found in res.stats.zones_found.items():
        label = {
            "greeting": "LỜI CHÀO",
            "opening": "MỞ TRUYỆN",
            "introduction": "GIỚI THIỆU",
            "development": "TRIỂN KHAI",
            "climax": "CAO TRÀO",
            "falling": "HẠ MÀN",
            "ending": "KẾT TRUYỆN",
            "farewell": "TẠM BIỆT",
        }[zone]
        status = "[OK]" if found else "[MISSING]"
        print(f"    {status} {label}")

    print()
    if res.stats.unknown_tag_count > 0:
        print(f"- Tag lạ (unknown) tổng: {res.stats.unknown_tag_count}")
        for tag, count in res.stats.unknown_tags.items():
            print(f"    [{tag}] x {count}")
        print()

    if res.errors:
        print("✘ LỖI (ERRORS):")
        for e in res.errors:
            ln = f" (line {e.line_no})" if e.line_no > 0 else ""
            print(f"  - {e.message}{ln}")
            if e.line_text:
                print(f"    >> {e.line_text}")
        print()
    else:
        print("✔  Không có lỗi nghiêm trọng (errors).")
        print()

    if res.warnings:
        print("⚠ CẢNH BÁO (WARNINGS):")
        for w in res.warnings:
            ln = f" (line {w.line_no})" if w.line_no > 0 else ""
            print(f"  - {w.message}{ln}")
            if w.line_text:
                print(f"    >> {w.line_text}")
        print()
    else:
        print("✔  Không có cảnh báo.")
        print()

    print("=" * 60)
    print("KẾT LUẬN:", "OK" if res.ok else "CAN SUA")
    print("=" * 60)


###############################################################################
# CLI
###############################################################################

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate audio-story plain script before rendering.")
    parser.add_argument("-i", "--input", required=True, help="Path to plain script .txt")
    parser.add_argument("--json", action="store_true", help="Print JSON report instead of text output")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    setup_stdio()
    used_files = UsedFilesTracker()
    parser = argparse.ArgumentParser(
        description="Validate renderer plain script trước khi render audio."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        required=True,
        help="Đường dẫn file renderer plain script .txt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Xuất kết quả dạng JSON (thay vì dạng text dễ đọc).",
    )
    args = parser.parse_args()

    file_path = Path(args.input)
    if not file_path.is_file():
        print(f"Input file not found: {file_path}")
        raise SystemExit(1)

    used_files.add("Input plain script", file_path)
    lines = load_text_file(file_path)
    res = validate_script(lines)

    if args.json:
        print(json.dumps(result_to_dict(res), ensure_ascii=False, indent=2))
    else:
        print_human_readable(res, file_path)

    used_files.print_summary()

    # Exit code: 0 nếu ok, 1 nếu có error
    raise SystemExit(0 if res.ok else 1)


if __name__ == "__main__":
    main()
