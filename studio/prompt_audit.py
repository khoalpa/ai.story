"""CLI for deterministic prompt/artifact conformance auditing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from studio.artifact_validation import validate_project
from studio.prompt_contract import load_prompt_contract


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit story artifacts against the latest canonical prompt.")
    parser.add_argument("path", type=Path, help="Project output directory, stage2 checkpoint, or story.zip")
    parser.add_argument("--prompt", type=Path, help="Use an explicit ChatGPT_prompt_v*.*.*.txt")
    args = parser.parse_args(argv)
    contract = load_prompt_contract(args.prompt)
    results = validate_project(args.path, contract)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps([result.as_dict() for result in results], ensure_ascii=False, indent=2))
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
