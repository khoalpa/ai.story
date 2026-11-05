from __future__ import annotations

import json

from scripts.verify_prompt_release import verify
from studio.prompt_contract import load_prompt_contract, prompt_contract_for_version
from studio.workflow_builder import build_workflow_package
from tests.contracts.test_story_package_v520 import _stage1_files


def _stage1_files_v522() -> dict[str, bytes]:
    files = _stage1_files()
    for name in ("image_prompts.json", "validation_report.json"):
        value = json.loads(files[name])
        value["prompt_version"] = "5.2.2"
        files[name] = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return files


def test_v522_r3_is_current_and_release_evidence_is_reproducible() -> None:
    contract = load_prompt_contract()
    assert contract.version_label == "5.2.2"
    assert contract.image_prompt_version == "1.1"
    evidence = verify()
    assert evidence["status"] == "PASS"
    assert evidence["pipeline_deployment"] == "UNVERIFIED"
    assert evidence["not_run"]


def test_v522_stage1_accepts_complete_contract() -> None:
    payload, result = build_workflow_package(
        1, "CREATE", _stage1_files_v522(),
        contract=prompt_contract_for_version("5.2.2"),
    )
    assert payload.startswith(b"PK")
    assert result["status"] == "PASS"


def test_v522_stage1_accepts_optional_tokenizer_gate_as_not_applicable() -> None:
    files = _stage1_files_v522()
    report = json.loads(files["validation_report.json"])
    gate = next(row for row in report["checks"] if row["id"] == "IMAGE_PROMPT_T5_TOKENS")
    gate.update({
        "status": "NOT_APPLICABLE",
        "required": False,
        "details": "T5-512 gate removed by prompt revision r3; no tokenizer validation performed",
    })
    files["validation_report.json"] = json.dumps(
        report, ensure_ascii=False, separators=(",", ":")
    ).encode()
    payload, result = build_workflow_package(
        1, "CREATE", files, contract=prompt_contract_for_version("5.2.2")
    )
    assert payload.startswith(b"PK")
    assert result["status"] == "PASS"
