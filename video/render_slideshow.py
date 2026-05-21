from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Optional

from video import config
from video.command_builders import build_slideshow_ffmpeg_cmd
from video.ffmpeg_runner import (
    ensure_output_dir,
    ffmpeg_base_args,
    get_media_duration_seconds,
    run_ffmpeg,
)
from video.logging_utils import get_logger
from video.runtime_tools import is_available_tool
from video.slideshow_concat import (
    estimate_slideshow_duration as estimate_slideshow_duration_core,
)
from video.slideshow_concat import write_concat_list as write_concat_list_core
from video.subtitle_filters import build_vf_filter
from video.validation import collect_scene_images, validate_slideshow_inputs

logger = get_logger(__name__)


def estimate_slideshow_duration(
    image_count: int,
    duration_per_image: float,
    audio_duration: Optional[float] = None,
) -> float:
    return estimate_slideshow_duration_core(
        image_count,
        duration_per_image,
        audio_duration=audio_duration,
        match_audio=config.SLIDESHOW_MATCH_AUDIO,
        audio_match_epsilon=config.AUDIO_MATCH_EPSILON,
    )


def write_concat_list(
    images: list[Path],
    duration_per_image: float,
    out_list_file: Path,
    audio_duration: Optional[float] = None,
) -> None:
    write_concat_list_core(
        images=images,
        duration_per_image=duration_per_image,
        out_list_file=out_list_file,
        audio_duration=audio_duration,
        match_audio=config.SLIDESHOW_MATCH_AUDIO,
        audio_match_epsilon=config.AUDIO_MATCH_EPSILON,
    )


def make_slideshow_video(
    audio: Path,
    scenes_dir: Optional[Path],
    aspect: config.AspectRatio,
    output: Path,
    duration_per_image: float = 10.0,
    subtitle: Optional[Path] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> None:
    images = validate_slideshow_inputs(audio, scenes_dir)
    ensure_output_dir(output)
    if scenes_dir is not None:
        raw_images = collect_scene_images(scenes_dir)
        if images != raw_images:
            logger.info(
                "Slideshow zone mode: mapped images by opening/zone/outro before rendering."
            )

    vf_filter = build_vf_filter(aspect, subtitle)
    ffprobe_exe = config.get_ffprobe_exe()
    ffprobe_available = is_available_tool(ffprobe_exe)
    if config.SLIDESHOW_MATCH_AUDIO and not ffprobe_available:
        logger.warning(
            "SLIDESHOW_MATCH_AUDIO=1 but ffprobe was not found; audio duration cannot be matched. "
            "(Install ffprobe or disable this with SLIDESHOW_MATCH_AUDIO=0.)"
        )

    audio_dur = get_media_duration_seconds(audio)
    expected_out = estimate_slideshow_duration(
        len(images), duration_per_image, audio_duration=audio_dur
    )
    tmp_list_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ffconcat") as tmp:
            tmp_list_path = Path(tmp.name)
        write_concat_list(
            images=images,
            duration_per_image=duration_per_image,
            out_list_file=tmp_list_path,
            audio_duration=audio_dur,
        )
        cmd = build_slideshow_ffmpeg_cmd(
            ffmpeg_base=ffmpeg_base_args(),
            concat_list=tmp_list_path,
            audio=audio,
            output=output,
            vf_filter=vf_filter,
            video_codec=config.DEFAULT_VIDEO_CODEC,
            preset=config.DEFAULT_PRESET,
            crf=config.DEFAULT_CRF,
            tune=config.DEFAULT_TUNE_STILLIMAGE,
            audio_codec=config.DEFAULT_AUDIO_CODEC,
            audio_bitrate=config.DEFAULT_AUDIO_BITRATE,
            movflags=config.DEFAULT_MOVFLAGS,
        )
        run_ffmpeg(cmd, expected_duration_s=expected_out, progress_callback=progress_callback)
    finally:
        if tmp_list_path is not None:
            if config.KEEP_CONCAT_LIST:
                logger.info("KEEP_CONCAT_LIST=1 -> keeping concat list: %s", tmp_list_path)
            else:
                try:
                    tmp_list_path.unlink(missing_ok=True)
                except OSError:
                    pass
