from __future__ import annotations

from video.gui.state import (
    VIDEO_PROJECT_PATH_DEFAULTS_KEY,
    VIDEO_PROJECT_PATH_SYNC_KEY,
    capture_project_path_defaults,
    prepare_project_path_defaults,
)


def test_video_paths_survive_inactive_widget_cleanup() -> None:
    state: dict[str, object] = {
        VIDEO_PROJECT_PATH_DEFAULTS_KEY: {
            "project_directory": r"D:\Audio Story\DDKA-0902",
            "values": {
                "video_input_root": r"D:\Audio Story\DDKA-0902",
                "video_output_dir": r"D:\Audio Story\DDKA-0902",
                "video_audio_input": r"D:\Audio Story\DDKA-0902\story.wav",
            },
        }
    }
    prepare_project_path_defaults(state)
    assert state["video_input_root"] == r"D:\Audio Story\DDKA-0902"
    assert state["video_output_dir"] == r"D:\Audio Story\DDKA-0902"

    for key in ("video_input_root", "video_output_dir", "video_audio_input"):
        state.pop(key)
    prepare_project_path_defaults(state)

    assert state["video_audio_input"] == r"D:\Audio Story\DDKA-0902\story.wav"


def test_new_project_overrides_previous_video_widget_values() -> None:
    state: dict[str, object] = {
        VIDEO_PROJECT_PATH_SYNC_KEY: r"D:\old",
        "video_input_root": r"D:\manual",
        VIDEO_PROJECT_PATH_DEFAULTS_KEY: {
            "project_directory": r"D:\new",
            "values": {"video_input_root": r"D:\new"},
        },
    }
    prepare_project_path_defaults(state)
    assert state["video_input_root"] == r"D:\new"


def test_manual_video_path_edits_are_captured_durably() -> None:
    state: dict[str, object] = {
        "video_input_root": r"D:\manual",
        VIDEO_PROJECT_PATH_DEFAULTS_KEY: {
            "project_directory": r"D:\project",
            "values": {"video_input_root": r"D:\project"},
        },
    }
    capture_project_path_defaults(state)
    payload = state[VIDEO_PROJECT_PATH_DEFAULTS_KEY]
    assert isinstance(payload, dict)
    assert payload["values"]["video_input_root"] == r"D:\manual"
