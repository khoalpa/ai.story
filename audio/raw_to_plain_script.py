#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from audio.audio_story_spec import CANONICAL_CONTRACT_VERSION, PLAIN_SCRIPT_FORMAT_VERSION
from audio.cli_utils import UsedFilesTracker, setup_stdio


def build_min_header(title: str = "") -> str:
    lines = [
        f"# FORMAT: AUDIO_STORY_PLAIN v{PLAIN_SCRIPT_FORMAT_VERSION}",
        f"# CONTRACT_VERSION: {CANONICAL_CONTRACT_VERSION}",
    ]
    if title.strip():
        lines.append(f"# TITLE: {title.strip()}")
    lines.extend(["", "SCRIPT:", ""])
    return "\n".join(lines)


def has_script_marker(lines: list[str]) -> bool:
    return any(line.strip().upper().startswith("SCRIPT:") for line in lines)


def normalize_raw_lines(lines: list[str], default_voice: str = "NARRATOR", default_lang: str = "VI") -> list[str]:
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            out.append("")
            continue
        if line.startswith("#") or line.startswith("//") or line.upper().startswith("SCRIPT:"):
            out.append(raw.rstrip("\n"))
            continue
        if line.startswith("["):
            out.append(raw.rstrip("\n"))
            continue
        out.append(f"[{default_voice}][{default_lang}] {line}")
    return out


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert raw text into plain engine script with safe default tags.")
    parser.add_argument("-i", "--input", required=True)
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--default-voice", default="NARRATOR")
    parser.add_argument("--default-lang", default="VI")
    parser.add_argument("--no-header", action="store_true")
    parser.add_argument("--auto-en", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    setup_stdio()
    used = UsedFilesTracker()
    args = build_arg_parser().parse_args(argv)

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.is_file():
        raise SystemExit(f"Input file not found: {in_path}")
    used.add("Input raw text", in_path)
    used.add("Output plain script", out_path)

    lines = in_path.read_text(encoding="utf-8").splitlines()
    normalized = normalize_raw_lines(lines, default_voice=args.default_voice, default_lang=args.default_lang)
    final_text = "\n".join(normalized)
    if not args.no_header and not has_script_marker(lines):
        final_text = build_min_header(args.title) + final_text
    out_path.write_text(final_text, encoding="utf-8")
    print(f"OK: created plain script: {out_path}")
    used.print_summary()


if __name__ == "__main__":
    main()
