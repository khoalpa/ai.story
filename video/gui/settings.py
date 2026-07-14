from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import streamlit as st

from video import config
from video.asset_profile_utils import (
    list_asset_profiles,
    pick_default_asset_profile,
    resolve_profile_defaults,
)
from video.config import DEFAULT_PROFILE_ROOT
from video.error_handling import USER_FACING_EXCEPTIONS, format_user_facing_error
from video.runtime_tools import collect_runtime_diagnostics
from video.providers.base import VideoProviderDescriptor
from video.providers.registry import get_video_provider_descriptors, normalize_video_provider
from common.gui.diagnostics_blocks import render_runtime_diagnostics_block
from common.gui.sidebar_sections import SidebarSection
from common.gui.user_messages import show_path_warning


_LOGLEVEL_OPTIONS = ["quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug", "trace"]
_SUBTITLE_POSITION_OPTIONS = ["bottom", "top", "middle"]


def _render_dependency_diagnostics(provider: VideoProviderDescriptor, settings: dict[str, Any]) -> None:
    collector = provider.collect_runtime_diagnostics
    report = collector(settings) if collector is not None else collect_runtime_diagnostics()
    render_runtime_diagnostics_block(report, serializer=lambda info: info.as_dict())


def _safe_ui_call(name: str, *args, **kwargs):
    fn = getattr(st, name, None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def _option_index(options: list[str], value: object, default: int = 0) -> int:
    try:
        return options.index(str(value))
    except ValueError:
        return default


def _render_advanced_encoding_settings() -> dict[str, Any]:
    with st.expander("Advanced encoding", expanded=False):
        video_codec = st.text_input("Video codec", value=str(config.DEFAULT_VIDEO_CODEC))
        audio_codec = st.text_input("Audio codec", value=str(config.DEFAULT_AUDIO_CODEC))
        audio_bitrate = st.text_input("Audio bitrate", value=str(config.DEFAULT_AUDIO_BITRATE))
        video_preset = st.text_input("Video preset", value=str(config.DEFAULT_PRESET))
        video_crf = st.number_input("CRF", min_value=0, max_value=63, value=int(config.DEFAULT_CRF), step=1)
        video_fps = st.number_input("FPS (static mode)", min_value=1, max_value=120, value=int(config.DEFAULT_FPS), step=1)
        video_tune = st.text_input("Video tune", value=str(config.DEFAULT_TUNE_STILLIMAGE))
        video_movflags = st.text_input("MP4 movflags", value=str(config.DEFAULT_MOVFLAGS))
    return {
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "audio_bitrate": audio_bitrate,
        "video_preset": video_preset,
        "video_crf": int(video_crf),
        "video_fps": int(video_fps),
        "video_tune": video_tune,
        "video_movflags": video_movflags,
    }


def _render_subtitle_style_settings() -> dict[str, Any]:
    with st.expander("Subtitle styling", expanded=False):
        subtitle_position = st.selectbox(
            "Subtitle position",
            options=_SUBTITLE_POSITION_OPTIONS,
            index=_option_index(_SUBTITLE_POSITION_OPTIONS, "bottom"),
        )
        subtitle_font_size = st.number_input("Subtitle font size", min_value=1, max_value=200, value=8, step=1)
        subtitle_outline = st.number_input("Subtitle outline", min_value=0, max_value=20, value=2, step=1)
        subtitle_shadow = st.number_input("Subtitle shadow", min_value=0, max_value=20, value=0, step=1)
        subtitle_alignment_raw = st.text_input("Subtitle alignment override", value="")
        subtitle_margin_l = st.number_input("Subtitle margin left", min_value=0, max_value=1000, value=40, step=5)
        subtitle_margin_r = st.number_input("Subtitle margin right", min_value=0, max_value=1000, value=40, step=5)
        subtitle_margin_v = st.number_input("Subtitle margin vertical", min_value=0, max_value=1000, value=240, step=5)
        subtitle_force_style = st.text_input("Subtitle force style override", value="")
    subtitle_alignment = int(subtitle_alignment_raw) if subtitle_alignment_raw.strip().isdigit() else None
    return {
        "subtitle_position": subtitle_position,
        "subtitle_font_size": int(subtitle_font_size),
        "subtitle_outline": int(subtitle_outline),
        "subtitle_shadow": int(subtitle_shadow),
        "subtitle_alignment": subtitle_alignment,
        "subtitle_margin_l": int(subtitle_margin_l),
        "subtitle_margin_r": int(subtitle_margin_r),
        "subtitle_margin_v": int(subtitle_margin_v),
        "subtitle_force_style": subtitle_force_style.strip() or None,
    }


def _render_slideshow_behavior_settings() -> dict[str, Any]:
    with st.expander("Slideshow behavior", expanded=False):
        slideshow_match_audio = st.checkbox("Match slideshow length to audio", value=bool(config.SLIDESHOW_MATCH_AUDIO))
        zone_aware_slideshow = st.checkbox(
            "Use story zones to time images",
            value=bool(config.SLIDESHOW_ZONE_AWARE),
            key="zone_aware_slideshow",
            help="When enabled, slideshow image durations come from story.json zones and subtitle timestamps.",
        )
        audio_match_epsilon = st.number_input(
            "Audio match epsilon",
            min_value=0.0,
            max_value=10.0,
            value=float(config.AUDIO_MATCH_EPSILON),
            step=0.1,
        )
        keep_concat_list = st.checkbox("Keep temporary ffconcat list", value=bool(config.KEEP_CONCAT_LIST))
    return {
        "slideshow_match_audio": bool(slideshow_match_audio),
        "zone_aware_slideshow": bool(zone_aware_slideshow),
        "audio_match_epsilon": float(audio_match_epsilon),
        "keep_concat_list": bool(keep_concat_list),
    }


def _render_ffmpeg_debug_settings() -> dict[str, Any]:
    with st.expander("FFmpeg logging/debug", expanded=False):
        ffmpeg_loglevel = st.selectbox(
            "FFmpeg loglevel",
            options=_LOGLEVEL_OPTIONS,
            index=_option_index(_LOGLEVEL_OPTIONS, config.FFMPEG_LOGLEVEL, default=4),
        )
        ffmpeg_stats = st.checkbox("Show FFmpeg stats", value=bool(config.FFMPEG_STATS))
        ffmpeg_stream_log = st.checkbox("Stream FFmpeg log directly", value=bool(config.FFMPEG_STREAM_LOG))
        show_progress = st.checkbox("Parse FFmpeg progress", value=bool(config.SHOW_PROGRESS))
        stderr_tail_lines = st.number_input("stderr tail lines", min_value=1, max_value=500, value=int(config.STDERR_TAIL_LINES), step=1)
        print_ffmpeg_version = st.checkbox("Print FFmpeg version during tool check", value=bool(config.PRINT_FFMPEG_VERSION))
        debug_ffmpeg_exe = st.checkbox("Debug FFmpeg executable path", value=False)
    return {
        "ffmpeg_loglevel": ffmpeg_loglevel,
        "ffmpeg_stats": bool(ffmpeg_stats),
        "ffmpeg_stream_log": bool(ffmpeg_stream_log),
        "show_progress": bool(show_progress),
        "stderr_tail_lines": int(stderr_tail_lines),
        "print_ffmpeg_version": bool(print_ffmpeg_version),
        "debug_ffmpeg_exe": bool(debug_ffmpeg_exe),
    }


def _render_persistent_history_settings() -> dict[str, Any]:
    with st.expander("Persistent history", expanded=False):
        history_dir = st.text_input("History directory override", value="")
        history_file = st.text_input("History file override", value="")
        st.caption("Leave both empty to use the default ~/.render_video history and logs.")
    return {
        "render_video_history_dir": history_dir.strip(),
        "render_video_history_file": history_file.strip(),
    }


def get_video_settings() -> dict[str, Any]:
    with st.sidebar:
        st.header(SidebarSection.PROFILES)
        profile_root = st.text_input("Profile root", value=str(DEFAULT_PROFILE_ROOT))
        profiles = list_asset_profiles(profile_root)
        profile_options = ["", *profiles]
        default_profile = pick_default_asset_profile(profiles)
        default_index = profile_options.index(default_profile) if default_profile else 0
        asset_profile = st.selectbox(
            "Asset profile",
            options=profile_options,
            index=default_index,
            help="Leave empty if you do not want to use a profile",
        )

        defaults: dict[str, Optional[Path]] = {
            "profile_dir": None,
            "cover": None,
            "scenes_dir": None,
        }
        profile_error: Optional[str] = None
        if asset_profile:
            try:
                defaults = resolve_profile_defaults(profile_root, asset_profile)
            except USER_FACING_EXCEPTIONS as exc:
                profile_error = format_user_facing_error(exc)
        if profile_error:
            show_path_warning("asset profile", path_value=asset_profile, actions=[profile_error, "Check the profile root again or choose another profile."])
        elif asset_profile and defaults.get("profile_dir") is not None:
            _safe_ui_call("caption", f"Profile dir: {defaults['profile_dir']}")

        st.header(SidebarSection.PROVIDER)
        provider_descriptors = get_video_provider_descriptors()
        provider_options = list(provider_descriptors)
        selected_provider = normalize_video_provider(st.session_state.get("video_provider"))
        if selected_provider not in provider_options:
            selected_provider = provider_options[0]
        selected_provider = st.selectbox(
            "Video Provider",
            options=provider_options,
            index=provider_options.index(selected_provider),
            key="video_provider",
            format_func=lambda provider_id: provider_descriptors[provider_id].label,
        )
        provider_descriptor = provider_descriptors[selected_provider]
        st.caption(provider_descriptor.description)
        provider_settings = provider_descriptor.render_sidebar()
        provider_values = provider_settings.as_dict()

        st.header(SidebarSection.INPUTS_OUTPUTS)
        input_root = st.text_input("Input root", value="output")
        output_dir = st.text_input("Output directory", value="output")

        st.header(SidebarSection.RENDER)
        mode = st.radio("Mode", options=["static", "slideshow"], index=0, horizontal=True)
        aspect = st.selectbox("Aspect", options=["9x16", "16x9"], index=0)
        duration_per_image = st.number_input(
            "Duration per image (slideshow)", min_value=1.0, value=60.0, step=1.0
        )
        advanced_settings = {
            **_render_advanced_encoding_settings(),
            **_render_subtitle_style_settings(),
            **_render_slideshow_behavior_settings(),
            **_render_ffmpeg_debug_settings(),
            **_render_persistent_history_settings(),
        }

        with st.expander(SidebarSection.RUNTIME, expanded=True):
            _render_dependency_diagnostics(provider_descriptor, provider_values)

    return {
        **provider_values,
        "profile_root": profile_root,
        "input_root": input_root,
        "output_dir": output_dir,
        "profiles": profiles,
        "asset_profile": asset_profile,
        "defaults": defaults,
        "profile_error": profile_error,
        "mode": mode,
        "aspect": aspect,
        "duration_per_image": float(duration_per_image),
        **advanced_settings,
    }


def render_settings_sidebar() -> dict[str, Any]:
    return get_video_settings()


def get_settings() -> dict[str, Any]:
    return get_video_settings()


def render_settings() -> dict[str, Any]:
    return get_video_settings()


def render_sidebar() -> dict[str, Any]:
    return render_settings_sidebar()
