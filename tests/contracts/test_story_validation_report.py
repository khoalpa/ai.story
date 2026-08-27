from __future__ import annotations

import pytest

from studio.story_validation_report import _all_gates_pass, _validate_story_report


def _minimal_report() -> dict:
    return {
        "summary": {},
        "quality": {},
        "engagement": {},
        "gates": [{"status": "PASS"}],
        "scene_zone_map": [],
    }


def test_story_report_contract_accepts_required_sections() -> None:
    _validate_story_report(_minimal_report())


def test_story_report_contract_lists_missing_sections() -> None:
    with pytest.raises(ValueError, match="quality"):
        _validate_story_report({"summary": {}})


def test_all_gates_pass_requires_non_empty_gate_list() -> None:
    report = _minimal_report()
    assert _all_gates_pass(report)
    report["gates"] = []
    assert not _all_gates_pass(report)
