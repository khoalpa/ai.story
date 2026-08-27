from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from video.gui.view_model_utils import path_to_text, pick_mapping_values

_VIDEO_SETTINGS_FIELDS = (
    'mode',
    'aspect',
    'duration_per_image',
    'cover_first',
    'cover_duration',
    'outro_last',
    'outro_duration',
    'ffmpeg_exe',
    'ffprobe_exe',
    'video_codec',
    'encoding_profile',
    'loudness_profile',
    'quality_gate',
    'audio_codec',
    'audio_bitrate',
    'video_preset',
    'video_crf',
    'video_fps',
    'video_tune',
    'video_movflags',
    'slideshow_match_audio',
    'zone_aware_slideshow',
    'environment_overlays',
    'environment_overlay_intensity',
    'environment_overlay_fade',
    'environment_allow_lens_effects',
    'environment_global_film_grain',
    'audio_match_epsilon',
    'keep_concat_list',
    'show_subtitles',
    'subtitle_position',
    'subtitle_font',
    'subtitle_font_size',
    'subtitle_text_color',
    'subtitle_text_opacity',
    'subtitle_outline',
    'subtitle_shadow',
    'subtitle_background_color',
    'subtitle_background_opacity',
    'subtitle_alignment',
    'subtitle_margin_l',
    'subtitle_margin_r',
    'subtitle_margin_v',
    'subtitle_force_style',
    'ffmpeg_loglevel',
    'ffmpeg_stats',
    'ffmpeg_stream_log',
    'show_progress',
    'stderr_tail_lines',
    'print_ffmpeg_version',
    'debug_ffmpeg_exe',
    'render_video_history_dir',
    'render_video_history_file',
)


def build_video_run_summary(
    *,
    audio: Path,
    output: Path,
    subtitle: Optional[Path],
    story_json: Optional[Path],
    cover: Optional[Path],
    scenes_dir: Optional[Path],
    settings: dict[str, Any],
) -> dict[str, Any]:
    summary = pick_mapping_values(settings, _VIDEO_SETTINGS_FIELDS)
    summary.update({
        'audio': path_to_text(audio),
        'subtitle': path_to_text(subtitle),
        'story_json': path_to_text(story_json),
        'output': path_to_text(output),
        'cover': path_to_text(cover),
        'scenes_dir': path_to_text(scenes_dir),
    })
    return summary
