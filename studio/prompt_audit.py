"""CLI for deterministic prompt/artifact conformance auditing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from studio.artifact_validation import validate_project
from studio.prompt_contract import load_prompt_contract
from studio.summary_audit import audit_summary_package, is_summary_package


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Story or Summary artifacts against canonical contracts.")
    parser.add_argument("path", type=Path, help="Story/Summary project directory or ZIP package")
    parser.add_argument("--prompt", type=Path, help="Use an explicit story_prompt_v*.*.*.txt")
    parser.add_argument("--type", choices=("auto", "story", "summary"), default="auto", help="Artifact family; default auto-detects summary.json")
    args = parser.parse_args(argv)
    summary_mode = args.type == "summary" or (args.type == "auto" and is_summary_package(args.path))
    if summary_mode:
        result = audit_summary_package(args.path)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps([result.as_dict()], ensure_ascii=False, indent=2))
        return 1 if result.status == "FAIL" else 0
    contract = load_prompt_contract(args.prompt)
    results = validate_project(args.path, contract)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps([result.as_dict() for result in results], ensure_ascii=False, indent=2))
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
