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
from pathlib import Path
from typing import Sequence

from audio.cli_utils import UsedFilesTracker, setup_stdio
from audio.story_package_v416 import parse_story_text, render_plain_script


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a v4.1.6 story.json (schema 4.1.3) "
            "to plain engine script (.txt) for rendering."
        )
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to v4.1.6 story.json (schema 4.1.3).",
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
        data = parse_story_text(json_path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    try:
        plain_text = render_plain_script(data)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid plain script render input: {exc}") from exc

    out_path.write_text(plain_text, encoding="utf-8")
    print(f"OK: created renderer plain script: {out_path}")
    used_files.print_summary()


if __name__ == "__main__":
    main()
