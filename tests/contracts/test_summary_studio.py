from __future__ import annotations

import json
from pathlib import Path

from studio.navigation import WORKSPACE_KEYS, pipeline_step_for_workspace
from studio.summary_package import canonical_json_bytes
from studio.summary_studio import (
    apply_pending_summary_editor_update,
    parse_summary_text,
    queue_summary_editor_update,
    summary_metrics,
)
from tests.contracts.test_summary_projection import summary_fixture


def test_summary_studio_parses_current_canonical_document() -> None:
    document, errors = parse_summary_text(
        canonical_json_bytes(summary_fixture()).decode("utf-8")
    )

    assert errors == []
    assert document is not None
    assert summary_metrics(document) == {
        "Nguồn": 1,
        "Claims": 1,
        "Đoạn lời đọc": 1,
        "Số liệu": 1,
    }


def test_summary_studio_reports_invalid_json_and_schema() -> None:
    document, errors = parse_summary_text("{")
    assert document is None
    assert errors and "JSON không hợp lệ" in errors[0]

    document, errors = parse_summary_text(json.dumps({"schema_version": "1.1.0"}))
    assert document is not None
    assert errors


def test_summary_editor_updates_are_applied_on_the_next_render() -> None:
    state = {"summary_json_editor": "old"}

    queue_summary_editor_update(state, "new")

    assert state["summary_json_editor"] == "old"
    assert apply_pending_summary_editor_update(state) is True
    assert state["summary_json_editor"] == "new"
    assert apply_pending_summary_editor_update(state) is False


def test_pending_editor_update_is_applied_before_text_area_is_created() -> None:
    source = Path("studio/summary_studio.py").read_text(encoding="utf-8")
    render = source.index("def render_summary_studio_workspace")
    pending = source.index(
        "apply_pending_summary_editor_update(st.session_state)", render
    )
    editor = source.index('st.text_area("Canonical JSON"', render)

    assert pending < editor


def test_summary_workspace_is_registered_in_shell_navigation() -> None:
    assert "Summary Studio" in WORKSPACE_KEYS
    assert pipeline_step_for_workspace("Summary Studio", {}) == 1
    source = Path("studio/gui_entry.py").read_text(encoding="utf-8")
    assert '"Summary Studio": "Tóm tắt"' in source
    assert "render_summary_studio_workspace" in source


def test_summary_workspace_uses_five_step_task_flow() -> None:
    source = Path("studio/summary_studio.py").read_text(encoding="utf-8")
    assert (
        'SUMMARY_STEPS = ("Nguồn", "Trích xuất", "Nội dung", "Lời đọc & cảnh", "Xuất bản")'
        in source
    )
    assert "st.segmented_control(" in source
    assert '"Quy trình tóm tắt"' in source
