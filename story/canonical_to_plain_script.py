#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
canonical_to_plain_script.py

Convert canonical authoring JSON (meta + outline + script)
thành plain engine script (.txt) cho bước render.

Cách dùng
    python canonical_to_plain_script.py --input in/story.json --output in/story.txt

Liên quan:
- validate_plain_script.py
- make_audio_edge_tts.py
- make_video_from_audio.py
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from .audio_story_spec import render_plain_script, validate_canonical_authoring


def setup_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
            continue
        except Exception:
            pass
        buffer = getattr(stream, "buffer", None)
        if buffer is None:
            continue
        try:
            wrapped = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")
            setattr(sys, name, wrapped)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    setup_stdio()

    parser = argparse.ArgumentParser(
        description=(
            "Convert canonical authoring JSON (meta + outline + script) "
            "to plain engine script (.txt) for rendering."
        )
    )
    parser.add_argument(
        "-i", "--input", required=True,
        help="Path to authoring JSON with meta/outline/script."
    )
    parser.add_argument(
        "-o", "--output", required=True,
        help="Path to plain .txt engine script output."
    )
    args = parser.parse_args(argv)

    json_path = Path(args.input)
    out_path = Path(args.output)

    if not json_path.is_file():
        raise SystemExit(f"Input JSON not found: {json_path}")

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {json_path}: {exc}") from exc

    errors = validate_canonical_authoring(data)
    if errors:
        raise SystemExit("Invalid canonical authoring JSON:\n- " + "\n- ".join(errors))

    try:
        plain_text = render_plain_script(data)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid plain script render input: {exc}") from exc

    out_path.write_text(plain_text, encoding="utf-8")
    print(f"OK: created plain engine script: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
