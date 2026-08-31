from __future__ import annotations

from pathlib import Path

import pytest

from studio.project_context import (
    STORY_DIRECTORY_KEY,
    STORY_DIRECTORY_WIDGET_KEY,
    VIDEO_PROJECT_PATH_DEFAULTS_KEY,
    apply_project_directory,
    commit_story_directory_widget,
    prepare_story_directory_widget,
    project_path_defaults,
)


def test_project_defaults_cover_all_related_story_audio_and_video_paths(tmp_path: Path) -> None:
    defaults = project_path_defaults(tmp_path, aspect="16x9")
    root = str(tmp_path.resolve())
    assert defaults["studio_overview_output_dir"] == root
    assert defaults["story_studio_directory"] == root
    assert defaults["audio_output_dir"] == root
    assert defaults["video_input_root"] == root
    assert defaults["video_output_dir"] == root
    assert defaults["video_audio_input"] == str(tmp_path.resolve() / "story.wav")
    assert defaults["video_subtitle_input"] == str(tmp_path.resolve() / "story.srt")
    assert defaults["video_story_json_input"] == str(tmp_path.resolve() / "story.json")
    assert defaults["video_audio_handoff_manifest"] == str(tmp_path.resolve() / "audio_video_handoff.json")
    assert defaults["video_input_scenes_dir"] == str(tmp_path.resolve() / "landscape")
    assert defaults["video_input_cover_path"] == str(tmp_path.resolve() / "landscape" / "cover.png")
    assert defaults["video_output_input"] == str(tmp_path.resolve() / "video_landscape.mp4")


def test_portrait_project_defaults_follow_current_video_aspect(tmp_path: Path) -> None:
    defaults = project_path_defaults(tmp_path, aspect="9x16")
    assert defaults["video_input_scenes_dir"].endswith("portrait")
    assert defaults["video_output_input"].endswith("video_portrait.mp4")


def test_apply_project_directory_updates_state_atomically(tmp_path: Path) -> None:
    state: dict[str, object] = {"video_aspect": "9x16", "unrelated": "keep"}
    selected = apply_project_directory(state, tmp_path)
    assert selected == tmp_path.resolve()
    assert state["story_studio_directory"] == str(tmp_path.resolve())
    assert state["video_input_scenes_dir"] == str(tmp_path.resolve() / "portrait")
    payload = state[VIDEO_PROJECT_PATH_DEFAULTS_KEY]
    assert isinstance(payload, dict)
    assert payload["project_directory"] == str(tmp_path.resolve())
    assert payload["values"]["video_input_root"] == str(tmp_path.resolve())
    assert state["unrelated"] == "keep"


def test_apply_project_directory_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="không tồn tại"):
        apply_project_directory({}, tmp_path / "missing")


def test_story_widget_is_rehydrated_after_streamlit_cleans_inactive_widget(tmp_path: Path) -> None:
    old = tmp_path / "old"
    selected = tmp_path / "selected"
    old.mkdir()
    selected.mkdir()
    state: dict[str, object] = {
        STORY_DIRECTORY_KEY: str(old),
        STORY_DIRECTORY_WIDGET_KEY: str(old),
    }

    apply_project_directory(state, selected)
    state.pop(STORY_DIRECTORY_WIDGET_KEY)  # Streamlit cleanup while Story Studio is inactive.

    assert prepare_story_directory_widget(state, old) == str(selected.resolve())
    assert state[STORY_DIRECTORY_WIDGET_KEY] == str(selected.resolve())


def test_manual_story_directory_edit_is_committed_to_durable_state(tmp_path: Path) -> None:
    state: dict[str, object] = {STORY_DIRECTORY_WIDGET_KEY: str(tmp_path)}
    assert commit_story_directory_widget(state) == str(tmp_path)
    assert state[STORY_DIRECTORY_KEY] == str(tmp_path)


def test_story_directory_picker_is_separate_from_shared_project_root() -> None:
    source = Path("studio/project_context.py").read_text(encoding="utf-8")
    picker = source[source.index("def choose_story_directory"):source.index("\n\n__all__")]
    assert "STORY_DIRECTORY_KEY" in picker
    assert "STORY_DIRECTORY_WIDGET_KEY" in picker
    assert "apply_project_directory" not in picker

    workspace = Path("studio/story_studio.py").read_text(encoding="utf-8")
    assert 'key="story_choose_package_directory"' in workspace
    assert "on_click=choose_story_directory" in workspace


def test_audio_and_video_settings_expose_synchronized_widget_keys() -> None:
    audio = Path("audio/gui/settings.py").read_text(encoding="utf-8")
    video = Path("video/gui/settings.py").read_text(encoding="utf-8")
    assert 'key="audio_output_dir"' in audio
    assert 'key="video_input_root"' in video
    assert 'key="video_output_dir"' in video
    assert 'key="video_aspect"' in video
