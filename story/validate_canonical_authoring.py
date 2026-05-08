#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

ITEMS_PER_MINUTE = 12

from .cli_utils import setup_stdio
from .audio_story_spec import validate_canonical_authoring

AUTO_REPAIR_LOG_KEYS = (
    "_auto_repair_log",
    "_repair_log",
    "repair_log",
)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Lỗi JSON ở file {path}: {exc}") from exc



def validate_script_length_rule(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []

    meta = data.get("meta")
    script = data.get("script")
    if not isinstance(meta, dict) or not isinstance(script, list):
        return []

    length_min = meta.get("length_min")
    if not isinstance(length_min, int) or length_min < 1:
        return []

    required_min_items = length_min * ITEMS_PER_MINUTE
    actual_items = len(script)
    if actual_items < required_min_items:
        return [
            (
                f"script too short: got {actual_items} items, required at least {required_min_items} items "
                f"(meta.length_min={length_min}, rule={ITEMS_PER_MINUTE} items/min)"
            )
        ]
    return []



def _coerce_log_entry(entry: Any) -> Dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None

    normalized: Dict[str, Any] = {
        "source_index": entry.get("source_index", entry.get("index", entry.get("original_index"))),
        "zone": entry.get("zone"),
        "environment": entry.get("environment"),
        "voice": entry.get("voice"),
        "speed": entry.get("speed"),
        "lang": entry.get("lang"),
        "split_count": entry.get("split_count", entry.get("sentence_count", entry.get("count"))),
        "original_text": entry.get("original_text", entry.get("text_before", entry.get("source_text"))),
        "sentences": entry.get("sentences", entry.get("texts_after", entry.get("parts", []))),
        "reason": entry.get("reason", "auto_split_multi_sentence"),
    }

    if not normalized["original_text"] and not normalized["sentences"]:
        return None
    return normalized



def extract_auto_repair_log(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, dict):
        return []

    candidates: List[Any] = []

    for key in AUTO_REPAIR_LOG_KEYS:
        if key in data:
            candidates.append(data.get(key))

    meta = data.get("meta")
    if isinstance(meta, dict):
        for key in AUTO_REPAIR_LOG_KEYS:
            if key in meta:
                candidates.append(meta.get(key))

    normalized_logs: List[Dict[str, Any]] = []
    for block in candidates:
        if not isinstance(block, list):
            continue
        for entry in block:
            item = _coerce_log_entry(entry)
            if item is not None:
                normalized_logs.append(item)

    return normalized_logs



def _format_auto_repair_log(logs: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for idx, item in enumerate(logs, start=1):
        src_idx = item.get("source_index")
        zone = item.get("zone") or "?"
        split_count = item.get("split_count")
        reason = item.get("reason") or "auto_split_multi_sentence"
        original = str(item.get("original_text") or "").strip()
        sentences = item.get("sentences") or []
        if not isinstance(sentences, list):
            sentences = [str(sentences)]

        header = f"[{idx}] source_index={src_idx} zone={zone} split_count={split_count} reason={reason}"
        lines.append(header)
        if original:
            lines.append(f"    original: {original}")
        for j, sent in enumerate(sentences, start=1):
            lines.append(f"    -> [{j}] {str(sent).strip()}")
    return lines



def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="Validate canonical authoring JSON (meta + outline + script array)."
    )
    parser.add_argument("-i", "--input", required=True, help="Đường dẫn file JSON canonical authoring.")
    parser.add_argument("--json", action="store_true", help="In kết quả dưới dạng JSON.")
    parser.add_argument(
        "--show-repair-log",
        action="store_true",
        help="In thêm auto-repair log nếu JSON có trường _auto_repair_log / repair_log.",
    )
    args = parser.parse_args(argv)

    path = Path(args.input)
    if not path.is_file():
        raise SystemExit(f"Input JSON file not found: {path}")

    data = _load_json(path)
    errors = validate_canonical_authoring(data)
    errors.extend(validate_script_length_rule(data))
    repair_log = extract_auto_repair_log(data)

    if args.json:
        payload = {
            "ok": not errors,
            "errors": errors,
            "input": str(path),
            "auto_repair_log_count": len(repair_log),
        }
        if args.show_repair_log:
            payload["auto_repair_log"] = repair_log
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if errors:
            print("[ERROR] Canonical authoring invalid:")
            for err in errors:
                print(f"- {err}")
        else:
            print(f"[OK] Canonical authoring valid: {path}")

        if repair_log:
            print(f"[INFO] Auto-repair entries detected: {len(repair_log)}")
            if args.show_repair_log:
                for line in _format_auto_repair_log(repair_log):
                    print(line)
        elif args.show_repair_log:
            print("[INFO] No auto-repair log found in input JSON.")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
