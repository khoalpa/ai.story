"""Shared project-directory selection and cross-workspace path defaults."""
from __future__ import annotations

from pathlib import Path
from typing import Any, MutableMapping

PROJECT_DIRECTORY_KEY = "studio_project_data_dir"
OVERVIEW_DIRECTORY_KEY = "studio_overview_output_dir"
STORY_DIRECTORY_KEY = "story_studio_directory"
STORY_DIRECTORY_WIDGET_KEY = "story_studio_directory_input"
STORY_PROJECT_SYNC_KEY = "story_studio_project_directory_seen"
VIDEO_PROJECT_PATH_DEFAULTS_KEY = "video_project_path_defaults"


def project_path_defaults(directory: Path, *, aspect: str = "landscape") -> dict[str, str]:
    root = directory.expanduser().resolve()
    normalized_aspect = "portrait" if aspect.casefold() in {"portrait", "9x16"} else "landscape"
    video_name = f"video_{normalized_aspect}.mp4"
    scenes = root / normalized_aspect
    cover = scenes / "cover.png"
    return {
        PROJECT_DIRECTORY_KEY: str(root),
        OVERVIEW_DIRECTORY_KEY: str(root),
        STORY_DIRECTORY_KEY: str(root),
        "audio_output_dir": str(root),
        "video_input_root": str(root),
        "video_output_dir": str(root),
        "video_audio_input": str(root / "story.wav"),
        "video_subtitle_input": str(root / "story.srt"),
        "video_story_json_input": str(root / "story.json"),
        "video_audio_handoff_manifest": str(root / "audio_video_handoff.json"),
        "video_input_cover_path": str(cover),
        "video_input_scenes_dir": str(scenes),
        "video_auto_cover_path": str(cover),
        "video_auto_scenes_dir": str(scenes),
        "video_output_input": str(root / video_name),
        "video_auto_output_path": str(root / video_name),
    }


def apply_project_directory(
    state: MutableMapping[str, Any], directory: str | Path
) -> Path:
    path = Path(str(directory).strip()).expanduser()
    if not path.is_dir():
        raise ValueError(f"Thư mục không tồn tại: {path}")
    aspect = str(state.get("video_aspect") or "16x9")
    defaults = project_path_defaults(path, aspect=aspect)
    previous = state.get(PROJECT_DIRECTORY_KEY)
    if previous and str(Path(str(previous)).resolve()) != str(path.resolve()):
        for key in ("last_result_summary", "audio_last_output", "audio_last_srt_output", "video_last_summary", "video_last_output", "story_evidence_range"):
            state.pop(key, None)
    state.update(defaults)
    state[VIDEO_PROJECT_PATH_DEFAULTS_KEY] = {
        "project_directory": defaults[PROJECT_DIRECTORY_KEY],
        "values": {
            key: value for key, value in defaults.items() if key.startswith("video_")
        },
    }
    state.pop("studio_project_directory_error", None)
    return Path(defaults[PROJECT_DIRECTORY_KEY])


def prepare_story_directory_widget(state: MutableMapping[str, Any], default: str | Path) -> str:
    """Hydrate the transient Story widget from durable cross-workspace state.

    Streamlit removes widget-owned keys when a widget is not rendered. Keeping the
    project value under a non-widget key prevents workspace navigation from losing it.
    """
    project_directory = str(state.get(PROJECT_DIRECTORY_KEY) or "").strip()
    previously_synced = str(state.get(STORY_PROJECT_SYNC_KEY) or "").strip()
    if project_directory and project_directory != previously_synced:
        desired = project_directory
        state[STORY_PROJECT_SYNC_KEY] = project_directory
    else:
        desired = str(
            state.get(STORY_DIRECTORY_KEY)
            or project_directory
            or Path(str(default)).expanduser().resolve()
        )
    state[STORY_DIRECTORY_KEY] = desired
    state[STORY_DIRECTORY_WIDGET_KEY] = desired
    return desired


def commit_story_directory_widget(state: MutableMapping[str, Any]) -> str:
    """Commit a manually edited Story directory back to durable state."""
    value = str(state.get(STORY_DIRECTORY_WIDGET_KEY) or "").strip()
    state[STORY_DIRECTORY_KEY] = value
    return value


def existing_picker_directory(value: str | Path) -> str:
    candidate = Path(str(value or "")).expanduser()
    if candidate.is_file():
        return str(candidate.parent)
    if candidate.is_dir():
        return str(candidate)
    for parent in candidate.parents:
        if parent.is_dir():
            return str(parent)
    return str(Path.cwd())


def choose_project_directory(state: MutableMapping[str, Any]) -> str | None:
    """Open the native folder picker and synchronize all project defaults."""
    root = None
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=root,
            initialdir=existing_picker_directory(
                str(state.get(OVERVIEW_DIRECTORY_KEY) or state.get(PROJECT_DIRECTORY_KEY) or "")
            ),
            mustexist=True,
            title="Chọn thư mục dữ liệu dự án",
        )
        if selected:
            apply_project_directory(state, selected)
            return selected
        state.pop("studio_project_directory_error", None)
        return None
    except Exception as exc:
        state["studio_project_directory_error"] = f"Không thể mở hộp thoại chọn thư mục: {exc}"
        return None
    finally:
        if root is not None:
            root.destroy()


def choose_story_directory(state: MutableMapping[str, Any]) -> str | None:
    """Choose a Story package directory without changing the shared project root."""
    root = None
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=root,
            initialdir=existing_picker_directory(
                str(state.get(STORY_DIRECTORY_KEY) or state.get(PROJECT_DIRECTORY_KEY) or "")
            ),
            mustexist=True,
            title="Chọn thư mục gói nội dung",
        )
        if selected:
            value = str(Path(selected).expanduser().resolve())
            state[STORY_DIRECTORY_KEY] = value
            state[STORY_DIRECTORY_WIDGET_KEY] = value
            state.pop("story_studio_directory_error", None)
            return value
        state.pop("story_studio_directory_error", None)
        return None
    except Exception as exc:
        state["story_studio_directory_error"] = f"Không thể mở hộp thoại chọn thư mục: {exc}"
        return None
    finally:
        if root is not None:
            root.destroy()


__all__ = [
    "OVERVIEW_DIRECTORY_KEY", "PROJECT_DIRECTORY_KEY", "STORY_DIRECTORY_KEY",
    "STORY_PROJECT_SYNC_KEY",
    "VIDEO_PROJECT_PATH_DEFAULTS_KEY",
    "STORY_DIRECTORY_WIDGET_KEY", "apply_project_directory", "choose_project_directory",
    "choose_story_directory",
    "commit_story_directory_widget", "existing_picker_directory",
    "prepare_story_directory_widget", "project_path_defaults",
]
