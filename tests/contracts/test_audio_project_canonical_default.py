from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio.gui.state import PENDING_PLAIN_SCRIPT_KEY
from audio.gui.workspace import (
    CANONICAL_PROJECT_SOURCE_KEY,
    _queue_plain_script_from_canonical,
    load_project_canonical_default,
)
from studio.project_context import PROJECT_DIRECTORY_KEY
from studio.summary_stages import build_summary_stage1
from studio.workflow_package import read_archive
from tests.contracts.test_summary_projection import summary_fixture


def test_audio_loads_verified_v416_project_by_default(sample_stage1_project: Path) -> None:
    story = sample_stage1_project / "story.json"
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(sample_stage1_project)}

    assert load_project_canonical_default(state) == story.resolve()
    assert json.loads(str(state["canonical_json_text"]))["schema_version"] == "4.1.3"
    assert state[CANONICAL_PROJECT_SOURCE_KEY] == str(story.resolve())
    assert "SCRIPT:" in str(state[PENDING_PLAIN_SCRIPT_KEY])


def test_audio_does_not_overwrite_canonical_edits_on_rerun(sample_stage1_project: Path) -> None:
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(sample_stage1_project)}
    load_project_canonical_default(state)
    state["canonical_json_text"] = '{"edited":true}'
    state["canonical_editor"] = '{"edited":true}'

    load_project_canonical_default(state)

    assert state["canonical_editor"] == '{"edited":true}'


def test_audio_rejects_project_without_current_manifest(tmp_path: Path) -> None:
    (tmp_path / "story.json").write_text('{"schema_version":"3.16"}', encoding="utf-8")
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(tmp_path)}
    with pytest.raises(ValueError, match="v4.1.6"):
        load_project_canonical_default(state)


def test_audio_loads_story_projection_from_complete_summary_directory(tmp_path: Path) -> None:
    package = build_summary_stage1(summary_fixture(), tmp_path / "summary_stage1.zip")
    root = tmp_path / "summary"
    root.mkdir()
    for name, raw in read_archive(package).items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(root)}

    assert load_project_canonical_default(state) == (root / "story.json").resolve()
    assert state["audio_story_package_kind"] == "SUMMARY"
    assert state["audio_story_package_stage"] == "SUMMARY_STAGE1"
    assert "SCRIPT:" in str(state[PENDING_PLAIN_SCRIPT_KEY])


def test_audio_rejects_tampered_story_projection_in_summary_directory(tmp_path: Path) -> None:
    package = build_summary_stage1(summary_fixture(), tmp_path / "summary_stage1.zip")
    root = tmp_path / "summary"
    root.mkdir()
    for name, raw in read_archive(package).items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    (root / "story.json").write_bytes((root / "story.json").read_bytes() + b" ")

    with pytest.raises(ValueError, match="Summary package không đạt audit"):
        load_project_canonical_default({PROJECT_DIRECTORY_KEY: str(root)})


def test_audio_leaves_editor_unchanged_when_project_has_no_story(tmp_path: Path) -> None:
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(tmp_path), "canonical_editor": "manual"}
    assert load_project_canonical_default(state) is None
    assert state["canonical_editor"] == "manual"


def test_queue_plain_script_from_canonical_generates_required_marker(sample_stage1_project: Path) -> None:
    canonical = (sample_stage1_project / "story.json").read_text(encoding="utf-8")
    state: dict[str, object] = {}

    _queue_plain_script_from_canonical(state, canonical)

    plain = str(state[PENDING_PLAIN_SCRIPT_KEY])
    assert "\nSCRIPT:\n" in plain


def test_empty_plain_script_is_an_empty_state_not_a_syntax_error() -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string(
        "from audio.gui.workspace import render_workspace_tab\nrender_workspace_tab()",
        default_timeout=20,
    ).run()

    assert not app.exception
    assert any("Chưa có kịch bản" in item.value for item in app.info)
    assert not any("Syntax check found" in item.value for item in app.error)
