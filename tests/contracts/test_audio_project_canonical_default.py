from __future__ import annotations

from pathlib import Path

from audio.gui.workspace import (
    CANONICAL_PROJECT_SOURCE_KEY,
    load_project_canonical_default,
)
from studio.project_context import PROJECT_DIRECTORY_KEY


def test_audio_loads_story_json_from_project_directory_by_default(tmp_path: Path) -> None:
    story = tmp_path / "story.json"
    story.write_text('{"title":"Project story"}', encoding="utf-8")
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(tmp_path)}

    assert load_project_canonical_default(state) == story.resolve()
    assert state["canonical_json_text"] == '{"title":"Project story"}'
    assert state["canonical_editor"] == '{"title":"Project story"}'
    assert state[CANONICAL_PROJECT_SOURCE_KEY] == str(story.resolve())


def test_audio_does_not_overwrite_canonical_edits_on_rerun(tmp_path: Path) -> None:
    story = tmp_path / "story.json"
    story.write_text('{"title":"Disk"}', encoding="utf-8")
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(tmp_path)}
    load_project_canonical_default(state)
    state["canonical_json_text"] = '{"title":"Edited"}'
    state["canonical_editor"] = '{"title":"Edited"}'

    load_project_canonical_default(state)

    assert state["canonical_editor"] == '{"title":"Edited"}'


def test_audio_loads_new_story_when_project_directory_changes(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "story.json").write_text("first", encoding="utf-8")
    (second / "story.json").write_text("second", encoding="utf-8")
    state: dict[str, object] = {PROJECT_DIRECTORY_KEY: str(first)}
    load_project_canonical_default(state)

    state[PROJECT_DIRECTORY_KEY] = str(second)
    load_project_canonical_default(state)

    assert state["canonical_editor"] == "second"


def test_audio_leaves_editor_unchanged_when_project_has_no_story(tmp_path: Path) -> None:
    state: dict[str, object] = {
        PROJECT_DIRECTORY_KEY: str(tmp_path),
        "canonical_editor": "manual",
    }

    assert load_project_canonical_default(state) is None
    assert state["canonical_editor"] == "manual"
