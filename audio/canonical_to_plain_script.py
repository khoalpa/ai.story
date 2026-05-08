#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
canonical_to_plain_script.py

Convert canonical authoring JSON (meta + outline + script)
thành renderer plain script (.txt) cho bước render.

Cách dùng
    canonical-to-plain --input in/story.json --output in/story.txt

Liên quan:
- validate-plain
- render-audio
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from audio.audio_story_spec import normalize_canonical_authoring_zones, render_plain_script, validate_canonical_authoring
from audio.cli_utils import UsedFilesTracker, setup_stdio


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert canonical authoring JSON (meta + outline + script) "
            "to plain engine script (.txt) for rendering."
        )
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to authoring JSON with meta/outline/script.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path to renderer plain script .txt output.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    setup_stdio()
    used_files = UsedFilesTracker()
    args = build_arg_parser().parse_args(argv)

    json_path = Path(args.input)
    out_path = Path(args.output)

    if not json_path.is_file():
        raise SystemExit(f"Input JSON not found: {json_path}")
    used_files.add("Input canonical JSON", json_path)
    used_files.add("Output plain script", out_path)

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {json_path}: {exc}") from exc

    data = normalize_canonical_authoring_zones(data)

    errors = validate_canonical_authoring(data)
    if errors:
        raise SystemExit("Invalid canonical authoring JSON:\n- " + "\n- ".join(errors))

    try:
        plain_text = render_plain_script(data)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid plain script render input: {exc}") from exc

    out_path.write_text(plain_text, encoding="utf-8")
    print(f"OK: created renderer plain script: {out_path}")
    used_files.print_summary()


if __name__ == "__main__":
    main()
