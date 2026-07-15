from __future__ import annotations

import argparse
import sys
from typing import Sequence

from video import __version__
MAPPING = {"render-video"}
DEFAULT_COMMAND = "render-video"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Unified CLI for Render Video. "
            "You can call it directly like 'render-video --audio ...' "
            "or keep using the legacy form 'render-video render-video --audio ...'."
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"render-video {__version__}",
    )
    return parser


def normalize_argv(argv: Sequence[str]) -> tuple[str, list[str]]:
    rest = list(argv)
    if rest and rest[0] in ("-h", "--help"):
        return DEFAULT_COMMAND, []
    if rest and rest[0] in MAPPING:
        return rest[0], rest[1:]
    return DEFAULT_COMMAND, rest


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    rest = list(sys.argv[1:] if argv is None else argv)
    if any(arg in ("--version", "-V") for arg in rest):
        parser.parse_args(["--version"])
        return

    command, normalized = normalize_argv(rest)

    if not normalized:
        parser.print_help()
        return

    from video import cli_entry

    cli_entry.main(normalized)


if __name__ == "__main__":
    main()
