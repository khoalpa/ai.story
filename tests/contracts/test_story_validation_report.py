from __future__ import annotations

import pytest

from studio.story_validation_report import _all_gates_pass, _validate_story_report


def _minimal_report() -> dict:
    return {
        "schema_version": "4.1.3", "prompt_version": "4.1.6", "stage": 1,
        "status": "COMPLETE", "input_sources": [], "checks": [],
        "limitations": [], "remaining_work": [], "archive_validation": {},
    }


def test_story_report_contract_accepts_required_sections() -> None:
    _validate_story_report(_minimal_report())


def test_story_report_contract_lists_missing_sections() -> None:
    report = _minimal_report()
    report.pop("checks")
    with pytest.raises(ValueError, match="checks"):
        _validate_story_report(report)


def test_all_gates_pass_requires_non_empty_gate_list() -> None:
    report = {"gates": [{"status": "PASS"}]}
    assert _all_gates_pass(report)
    report["gates"] = []
    assert not _all_gates_pass(report)
