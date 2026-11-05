"""Verify reproducible specification-level release evidence for prompt v5.2.2 r3."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"
RELEASE = ROOT / "docs" / "releases" / "v5.2.2-r3"
EXPECTED_PROMPT_SHA256 = "b5df7d75cd9c1de60a5513bb9cbc9f639b3d0cf1cdb2cd72e6135c1cf4f9ab0c"
EXPECTED_QUICKSTART_SHA256 = "0d23521ac463fcc5cf1e3953c2cc53cf8d262af8528e0761708b82dbe7d82f8b"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> dict[str, Any]:
    prompt = PROMPTS / "ChatGPT_prompt_v5.2.2.txt"
    quickstart = PROMPTS / "ChatGPT_prompt_v5.2.2_Quickstart.txt"
    policy_path = RELEASE / "release_policy_v5.2.2_r3.json"
    report_path = RELEASE / "Bao_cao_Prompt_v5.2.2_r3.md"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    prompt_text = prompt.read_text(encoding="utf-8")
    quickstart_text = quickstart.read_text(encoding="utf-8")
    checks = {
        "canonical_hash_matches_release": _sha256(prompt) == EXPECTED_PROMPT_SHA256,
        "quickstart_hash_matches_release": _sha256(quickstart) == EXPECTED_QUICKSTART_SHA256,
        "prompt_revision_r3": "REVISION r3" in prompt_text,
        "quickstart_revision_r3": "Revision: r3" in quickstart_text,
        "schema_versions_preserved": all(value in prompt_text for value in (
            'schema_version="4.1.3"', 'schema_version="5.0.0"',
            'image_prompt_version="1.1"', 'character_pack_version="1.0"',
        )),
        "runtime_tokenizer_gate_removed": (
            "IMAGE_PROMPT_T5_TOKENS" in prompt_text
            and "T5-512 gate removed by prompt revision r3" in prompt_text
        ),
        "policy_targets_v522_r3": (
            policy.get("target_prompt_version") == "5.2.2"
            and policy.get("prompt_revision") == "r3"
        ),
        "pipeline_remains_unverified": (
            policy.get("reporting", {}).get("pipeline_deployment") == "UNVERIFIED"
        ),
        "release_report_present": report_path.is_file(),
    }
    return {
        "evidence_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "prompt_version": "5.2.2",
        "prompt_revision": "r3",
        "release_label": "PRODUCTION_READY_SPEC",
        "pipeline_deployment": "UNVERIFIED",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "artifacts": {
            path.name: _sha256(path)
            for path in (prompt, quickstart, policy_path, report_path)
        },
        "not_run": [
            "native_tokenizer_production_test", "production_audio_test",
            "production_image_test", "real_end_to_end_pipeline",
            "79_formal_acceptance_execution",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = verify()
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
