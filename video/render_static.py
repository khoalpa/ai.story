from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from video import config
from video.command_builders import build_static_ffmpeg_cmd
from video.config import AspectRatio
from video.ffmpeg_runner import (
    ensure_output_dir,
    ffmpeg_base_args,
    get_media_duration_seconds,
    run_ffmpeg,
)
from video.subtitle_filters import build_vf_filter
from video.validation import validate_static_inputs


def make_static_video(
    audio: Path,
    cover: Optional[Path],
    aspect: AspectRatio,
    output: Path,
    subtitle: Optional[Path] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> None:
    validate_static_inputs(audio, cover)
    ensure_output_dir(output)
    assert cover is not None
    vf_filter = build_vf_filter(aspect, subtitle)
    audio_dur = get_media_duration_seconds(audio)
    cmd = build_static_ffmpeg_cmd(
        ffmpeg_base=ffmpeg_base_args(),
        cover=cover,
        audio=audio,
        output=output,
        vf_filter=vf_filter,
        video_codec=config.DEFAULT_VIDEO_CODEC,
        preset=config.DEFAULT_PRESET,
        crf=config.DEFAULT_CRF,
        tune=config.DEFAULT_TUNE_STILLIMAGE,
        fps=config.DEFAULT_FPS,
        audio_codec=config.DEFAULT_AUDIO_CODEC,
        audio_bitrate=config.DEFAULT_AUDIO_BITRATE,
        movflags=config.DEFAULT_MOVFLAGS,
        pixel_format=config.DEFAULT_PIXEL_FORMAT,
        color_primaries=config.DEFAULT_COLOR_PRIMARIES,
        color_transfer=config.DEFAULT_COLOR_TRANSFER,
        color_space=config.DEFAULT_COLOR_SPACE,
        color_range=config.DEFAULT_COLOR_RANGE,
        gop_seconds=config.DEFAULT_GOP_SECONDS,
    )
    run_ffmpeg(cmd, expected_duration_s=audio_dur, progress_callback=progress_callback)
