from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from video.command_builders import build_static_ffmpeg_cmd
from video.config import (
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_AUDIO_CODEC,
    DEFAULT_CRF,
    DEFAULT_FPS,
    DEFAULT_MOVFLAGS,
    DEFAULT_PRESET,
    DEFAULT_TUNE_STILLIMAGE,
    DEFAULT_VIDEO_CODEC,
    AspectRatio,
)
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
        video_codec=DEFAULT_VIDEO_CODEC,
        preset=DEFAULT_PRESET,
        crf=DEFAULT_CRF,
        tune=DEFAULT_TUNE_STILLIMAGE,
        fps=DEFAULT_FPS,
        audio_codec=DEFAULT_AUDIO_CODEC,
        audio_bitrate=DEFAULT_AUDIO_BITRATE,
        movflags=DEFAULT_MOVFLAGS,
    )
    run_ffmpeg(cmd, expected_duration_s=audio_dur, progress_callback=progress_callback)
