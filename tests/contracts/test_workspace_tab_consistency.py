from __future__ import annotations

from pathlib import Path

from audio.gui.view_registry import AUDIO_VIEW_SPECS, normalize_audio_view_id
from video.gui.view_registry import VIDEO_VIEW_SPECS, normalize_video_view_id

COMMON_VIEW_IDS = ("inputs", "run", "doctor", "test", "results_logs", "history")
COMMON_VIEW_LABELS = {
    "inputs": "Inputs",
    "run": "Run",
    "doctor": "Doctor",
    "test": "Test",
    "results_logs": "Results & Logs",
    "history": "History",
}


def _ids(specs) -> tuple[str, ...]:
    return tuple(spec.id for spec in specs)


def test_common_tabs_have_shared_ids_labels_and_order() -> None:
    audio_common = tuple(spec for spec in AUDIO_VIEW_SPECS if spec.id in COMMON_VIEW_IDS)
    video_common = tuple(spec for spec in VIDEO_VIEW_SPECS if spec.id in COMMON_VIEW_IDS)

    assert _ids(audio_common) == COMMON_VIEW_IDS
    assert _ids(video_common) == COMMON_VIEW_IDS
    assert {spec.id: spec.label for spec in audio_common} == COMMON_VIEW_LABELS
    assert {spec.id: spec.label for spec in video_common} == COMMON_VIEW_LABELS


def test_module_specific_tabs_are_explicit() -> None:
    assert _ids(AUDIO_VIEW_SPECS) == (
        "inputs",
        "run",
        "batch",
        "doctor",
        "test",
        "results_logs",
        "history",
    )
    assert _ids(VIDEO_VIEW_SPECS) == COMMON_VIEW_IDS


def test_legacy_labels_migrate_to_stable_ids() -> None:
    assert normalize_audio_view_id("Input") == "inputs"
    assert normalize_audio_view_id("Test TTS") == "test"
    assert normalize_audio_view_id("Preview & Logs") == "results_logs"
    assert normalize_video_view_id("Inputs") == "inputs"
    assert normalize_video_view_id("Preview & Logs") == "results_logs"


def test_main_panels_render_standalone_and_embedded_from_registry() -> None:
    for path, specs_name in (
        (Path("audio/gui/main_panel.py"), "AUDIO_VIEW_SPECS"),
        (Path("video/gui/main_panel.py"), "VIDEO_VIEW_SPECS"),
    ):
        content = path.read_text(encoding="utf-8")
        assert f"st.tabs([spec.label for spec in {specs_name}])" in content
        assert "format_func=lambda view_id:" in content
        assert 'st.segmented_control(\n        "Khu vực",' in content
        assert "st.radio(" not in content


def test_audio_history_and_story_studio_have_separate_owners() -> None:
    audio_panel = Path("audio/gui/main_panel.py").read_text(encoding="utf-8")
    audio_tabs = Path("audio/gui/tabs.py").read_text(encoding="utf-8")
    studio_shell = Path("studio/gui_entry.py").read_text(encoding="utf-8")

    assert '"history": render_history_tab' in audio_panel
    assert "render_run_history(_build_repository(settings), show_heading=False)" in audio_tabs
    assert "render_run_history(repository)" not in audio_tabs
    assert "Project Tools" not in audio_panel
    assert '"Story Studio": lambda: render_story_studio_workspace' in studio_shell
    assert '["Overview", "Story Studio", "Prompts", "Audio Studio", "Video Studio"]' in studio_shell
    assert '"Prompts": lambda: render_prompt_library_workspace' in studio_shell
    for legacy_workspace in ('"Story":', '"Validation":', '"Quality":', '"Anchor":', '"Tools":'):
        assert legacy_workspace not in studio_shell


def test_each_top_level_tab_has_a_consistent_intro() -> None:
    audio_tabs = Path("audio/gui/tabs.py").read_text(encoding="utf-8")
    video_tabs = Path("video/gui/tabs.py").read_text(encoding="utf-8")

    for label in COMMON_VIEW_LABELS.values():
        assert f'st.subheader("{label}")' in audio_tabs
        assert f'st.subheader("{label}")' in video_tabs
