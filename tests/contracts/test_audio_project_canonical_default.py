from __future__ import annotations

from pathlib import Path

import pytest

from audio.gui.workspace import (
    CANONICAL_PROJECT_SOURCE_KEY,
    load_project_canonical_default,
)
from studio.project_context import PROJECT_DIRECTORY_KEY


def test_audio_loads_verified_v416_project_by_default(sample_stage1_project: Path) -> None:
    story = sample_stage1_project / "story.json"
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(sample_stage1_project)}

    assert load_project_canonical_default(state) == story.resolve()
    assert '"schema_version": "4.1.3"' in str(state["canonical_json_text"])
    assert state[CANONICAL_PROJECT_SOURCE_KEY] == str(story.resolve())


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


def test_audio_leaves_editor_unchanged_when_project_has_no_story(tmp_path: Path) -> None:
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(tmp_path), "canonical_editor": "manual"}
    assert load_project_canonical_default(state) is None
    assert state["canonical_editor"] == "manual"
