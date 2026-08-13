#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""Public convenience imports for the Video renderer."""

import importlib
import warnings

from video.cli_entry import (
    build_parser,
    main,
    parse_args,
    run_from_args,
)
from video.render_slideshow import make_slideshow_video
from video.render_static import make_static_video
from video.validation import autodetect_subtitle_from_audio

__all__ = [
    "autodetect_subtitle_from_audio",
    "build_parser",
    "main",
    "make_slideshow_video",
    "make_static_video",
    "parse_args",
    "run_from_args",
]

_LEGACY_ALIAS_PATHS = {
    "build_scale_pad_filter": ("video.subtitle_filters", "build_scale_pad_filter"),
    "build_vf_filter": ("video.subtitle_filters", "build_vf_filter"),
    "build_zone_slideshow_images": ("video.validation", "build_zone_slideshow_images"),
    "collect_scene_images": ("video.validation", "collect_scene_images"),
    "ensure_output_dir": ("video.ffmpeg_runner", "ensure_output_dir"),
    "ensure_tools": ("video.ffmpeg_runner", "ensure_tools"),
    "escape_subtitle_path": ("video.subtitle_filters", "escape_subtitle_path"),
    "estimate_slideshow_duration": ("video.render_slideshow", "estimate_slideshow_duration"),
    "ffmpeg_base_args": ("video.ffmpeg_runner", "ffmpeg_base_args"),
    "format_hms": ("video.ffmpeg_runner", "format_hms"),
    "get_media_duration_seconds": ("video.ffmpeg_runner", "get_media_duration_seconds"),
    "run_ffmpeg": ("video.ffmpeg_runner", "run_ffmpeg"),
    "validate_slideshow_inputs": ("video.validation", "validate_slideshow_inputs"),
    "validate_static_inputs": ("video.validation", "validate_static_inputs"),
    "write_concat_list": ("video.render_slideshow", "write_concat_list"),
}


def __getattr__(name: str):
    if name in _LEGACY_ALIAS_PATHS:
        warnings.warn(
            f"render_video.make_video_from_audio.{name} is deprecated; import from the focused module instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        module_name, attr_name = _LEGACY_ALIAS_PATHS[name]
        module = importlib.import_module(module_name)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    main()
