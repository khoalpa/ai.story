from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="generator-story", description="Generator Story Project CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="Generate canonical JSON + plain script from brief")
    sub.add_parser("canonical-to-plain", help="Convert canonical JSON to plain script")
    sub.add_parser("convert-raw", help="Convert raw text to tagged plain script")
    sub.add_parser("validate-canonical", help="Validate canonical authoring JSON")
    sub.add_parser("validate-plain", help="Validate plain script")
    sub.add_parser("test-llm", help="Run a lightweight LLM connectivity test")
    return parser


def main() -> int:
    parser = build_parser()
    ns, rest = parser.parse_known_args()
    if ns.command == "generate":
        from . import generate_script
        return int(generate_script.main(rest) or 0)
    if ns.command == "canonical-to-plain":
        from . import canonical_to_plain_script
        return int(canonical_to_plain_script.main(rest) or 0)
    if ns.command == "convert-raw":
        from . import convert_raw_to_script
        return int(convert_raw_to_script.main(rest) or 0)
    if ns.command == "validate-canonical":
        from . import validate_canonical_authoring
        return int(validate_canonical_authoring.main(rest) or 0)
    if ns.command == "validate-plain":
        from . import validate_plain_script
        return int(validate_plain_script.main(rest) or 0)
    if ns.command == "test-llm":
        from .test_llm import main as test_llm_main
        return int(test_llm_main(rest) or 0)
    parser.error("Unknown command")
    return 2
