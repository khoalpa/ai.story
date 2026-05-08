from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from common.gui.view_model_utils import path_to_text, pick_mapping_values


_VIDEO_SETTINGS_FIELDS = (
    'mode',
    'aspect',
    'duration_per_image',
    'asset_profile',
    'profile_root',
    'ffmpeg_exe',
    'ffprobe_exe',
)


def build_video_run_summary(
    *,
    audio: Path,
    output: Path,
    subtitle: Optional[Path],
    cover: Optional[Path],
    scenes_dir: Optional[Path],
    settings: dict[str, Any],
) -> dict[str, Any]:
    summary = pick_mapping_values(settings, _VIDEO_SETTINGS_FIELDS)
    summary.update({
        'audio': path_to_text(audio),
        'subtitle': path_to_text(subtitle),
        'output': path_to_text(output),
        'cover': path_to_text(cover),
        'scenes_dir': path_to_text(scenes_dir),
    })
    return summary
