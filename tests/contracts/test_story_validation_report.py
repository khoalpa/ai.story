from __future__ import annotations

from pathlib import Path

import pytest

from studio.story_validation_report import (
    _all_gates_pass,
    _validate_story_report,
    effective_validation_status,
)


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


def test_package_failure_overrides_self_declared_complete_status() -> None:
    report = {"status": "COMPLETE"}
    inspection = {"overall_status": "FAIL", "publish_status": "FAIL"}

    assert effective_validation_status(report, inspection) == "FAIL"


def test_unverified_package_is_not_presented_as_validation_failure() -> None:
    report = {"status": "PARTIAL"}
    inspection = {"overall_status": "NOT_VERIFIED", "publish_status": "FAIL"}

    assert effective_validation_status(report, inspection) == "NOT_VERIFIED"


def test_standalone_report_keeps_its_declared_status() -> None:
    assert effective_validation_status({"status": "COMPLETE"}, None) == "COMPLETE"


def test_manual_review_submit_is_not_stuck_behind_form_checkbox() -> None:
    source = Path("studio/story_validation_report.py").read_text(encoding="utf-8")

    assert 'form_submit_button("Lưu kết quả kiểm định", type="primary")' in source
    assert "disabled=not confirmed" not in source
    assert "if not confirmed:" in source


def test_lineage_rebuild_separates_folder_save_from_zip_download() -> None:
    source = Path("studio/story_validation_report.py").read_text(encoding="utf-8")
    start = source.index("def _render_lineage_rebuild(")
    end = source.index("\ndef render_story_validation_report", start)
    body = source[start:end]

    assert 'save_column, download_column = st.columns(2, gap="large")' in body
    assert 'st.markdown("##### Lưu thành thư mục mới")' in body
    assert 'st.markdown("##### Tải file ZIP")' in body
    assert 'st.selectbox(' in body
    assert 'st.download_button(' in body
    assert body.index('"##### Lưu thành thư mục mới"') < body.index('"##### Tải file ZIP"')
