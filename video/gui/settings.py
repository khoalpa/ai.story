from __future__ import annotations

from typing import Any

import streamlit as st

from video import config
from video.encoding_profiles import PROFILE_CHOICES
from video.runtime_tools import collect_runtime_diagnostics
from video.providers.base import VideoProviderDescriptor
from video.providers.registry import get_video_provider_descriptors, normalize_video_provider
from video.gui.diagnostics_blocks import render_runtime_diagnostics_block
from video.gui.sidebar_sections import SidebarSection


_LOGLEVEL_OPTIONS = ["quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug", "trace"]
_SUBTITLE_POSITION_OPTIONS = ["bottom", "top", "middle"]
_SUBTITLE_FONT_OPTIONS = [
    "Arial",
    "Calibri",
    "Tahoma",
    "Verdana",
    "Trebuchet MS",
    "Times New Roman",
    "Georgia",
    "Courier New",
    "Noto Sans",
    "Noto Serif",
    "DejaVu Sans",
]


def _render_dependency_diagnostics(provider: VideoProviderDescriptor, settings: dict[str, Any]) -> None:
    collector = provider.collect_runtime_diagnostics
    report = collector(settings) if collector is not None else collect_runtime_diagnostics()
    render_runtime_diagnostics_block(report, expanded=True, serializer=lambda info: info.as_dict())


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
        encoding_profile = st.selectbox(
            "Encoding profile",
            options=list(PROFILE_CHOICES),
            index=_option_index(list(PROFILE_CHOICES), config.DEFAULT_ENCODING_PROFILE),
            help="auto selects YouTube 4K for 16:9 and TikTok 1080x1920 for 9:16.",
        )
        loudness_profile = st.selectbox(
            "Loudness profile",
            options=["narration", "social_video", "broadcast"],
            index=_option_index(["narration", "social_video", "broadcast"], config.DEFAULT_LOUDNESS_PROFILE),
        )
        quality_gate = st.checkbox("Video quality gate", value=bool(config.DEFAULT_QUALITY_GATE))
        custom_encoding = st.checkbox(
            "Custom encoder overrides",
            value=False,
            help="Leave disabled to use the selected encoding profile without manual overrides.",
        )
        video_codec = st.text_input("Video codec", value=str(config.DEFAULT_VIDEO_CODEC), disabled=not custom_encoding)
        audio_codec = st.text_input("Audio codec", value=str(config.DEFAULT_AUDIO_CODEC), disabled=not custom_encoding)
        audio_bitrate = st.text_input("Audio bitrate", value=str(config.DEFAULT_AUDIO_BITRATE), disabled=not custom_encoding)
        video_preset = st.text_input("Video preset", value=str(config.DEFAULT_PRESET), disabled=not custom_encoding)
        video_crf = st.number_input("CRF", min_value=0, max_value=63, value=int(config.DEFAULT_CRF), step=1, disabled=not custom_encoding)
        video_fps = st.number_input("FPS", min_value=1, max_value=120, value=int(config.DEFAULT_FPS), step=1, disabled=not custom_encoding)
        video_tune = st.text_input("Video tune", value=str(config.DEFAULT_TUNE_STILLIMAGE), disabled=not custom_encoding)
        video_movflags = st.text_input("MP4 movflags", value=str(config.DEFAULT_MOVFLAGS), disabled=not custom_encoding)
    return {
        "encoding_profile": encoding_profile,
        "loudness_profile": loudness_profile,
        "quality_gate": bool(quality_gate),
        "video_codec": video_codec if custom_encoding else None,
        "audio_codec": audio_codec if custom_encoding else None,
        "audio_bitrate": audio_bitrate if custom_encoding else None,
        "video_preset": video_preset if custom_encoding else None,
        "video_crf": int(video_crf) if custom_encoding else None,
        "video_fps": int(video_fps) if custom_encoding else None,
        "video_tune": video_tune if custom_encoding else None,
        "video_movflags": video_movflags if custom_encoding else None,
    }


def _render_subtitle_style_settings() -> dict[str, Any]:
    with st.expander("Subtitle styling", expanded=False):
        subtitle_position = st.selectbox(
            "Subtitle position",
            options=_SUBTITLE_POSITION_OPTIONS,
            index=_option_index(_SUBTITLE_POSITION_OPTIONS, "bottom"),
        )
        subtitle_font_size = st.number_input(
            "Subtitle font size",
            min_value=1,
            max_value=200,
            value=int(config.DEFAULT_SUBTITLE_FONT_SIZE),
            step=1,
        )
        subtitle_outline = st.number_input("Subtitle outline", min_value=0, max_value=20, value=2, step=1)
        subtitle_shadow = st.number_input("Subtitle shadow", min_value=0, max_value=20, value=0, step=1)
        default_background_opacity = max(
            0,
            min(100, int(config.DEFAULT_SUBTITLE_BACKGROUND_OPACITY)),
        )
        transparent_subtitle_background = st.checkbox(
            "Transparent subtitle outline",
            value=default_background_opacity == 0,
            help="Removes the colored outline around each glyph; no rectangular text box is used.",
        )
        font_column, text_color_column = st.columns(2)
        with font_column:
            subtitle_font = st.selectbox(
                "Subtitle font",
                options=_SUBTITLE_FONT_OPTIONS,
                index=_option_index(
                    _SUBTITLE_FONT_OPTIONS,
                    config.DEFAULT_SUBTITLE_FONT,
                ),
                help="The font must be installed on the machine that renders the video.",
            )
        with text_color_column:
            subtitle_text_color = st.color_picker(
                "Subtitle text color",
                value=str(config.DEFAULT_SUBTITLE_TEXT_COLOR),
            )
        background_color_column, background_opacity_column = st.columns(2)
        with background_color_column:
            subtitle_background_color = st.color_picker(
                "Subtitle outline color",
                value=str(config.DEFAULT_SUBTITLE_BACKGROUND_COLOR),
                disabled=transparent_subtitle_background,
            )
        with background_opacity_column:
            subtitle_background_opacity = st.slider(
                "Outline opacity (%)",
                min_value=0,
                max_value=100,
                value=default_background_opacity,
                help="Controls the outline around each glyph. Set to 0 for no colored outline.",
                disabled=transparent_subtitle_background,
            )
        subtitle_alignment_raw = st.text_input("Subtitle alignment override", value="")
        subtitle_margin_l = st.number_input("Subtitle margin left", min_value=0, max_value=1000, value=40, step=5)
        subtitle_margin_r = st.number_input("Subtitle margin right", min_value=0, max_value=1000, value=40, step=5)
        subtitle_margin_v = st.number_input("Subtitle margin vertical", min_value=0, max_value=1000, value=240, step=5)
        subtitle_force_style = st.text_input(
            "Subtitle force style override",
            value="",
            help="When set, this complete ASS style override takes precedence over the background controls above.",
        )
    subtitle_alignment = int(subtitle_alignment_raw) if subtitle_alignment_raw.strip().isdigit() else None
    return {
        "subtitle_position": subtitle_position,
        "subtitle_font": subtitle_font,
        "subtitle_font_size": int(subtitle_font_size),
        "subtitle_text_color": subtitle_text_color,
        "subtitle_outline": int(subtitle_outline),
        "subtitle_shadow": int(subtitle_shadow),
        "subtitle_background_color": subtitle_background_color,
        "subtitle_background_opacity": (
            0 if transparent_subtitle_background else int(subtitle_background_opacity)
        ),
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
            help="When enabled, slideshow image durations come from timeline zones and subtitle timestamps.",
        )
        cover_first = st.checkbox(
            "Use cover as first screen",
            value=bool(config.SLIDESHOW_COVER_FIRST),
            help="Shows the selected cover from the start of the video without extending the audio timeline.",
        )
        cover_duration = st.number_input(
            "Cover duration (seconds)",
            min_value=0.5,
            max_value=30.0,
            value=float(config.COVER_DURATION_SECONDS),
            step=0.5,
            disabled=not cover_first,
        )
        outro_last = st.checkbox(
            "Use outro as end screen",
            value=bool(config.SLIDESHOW_OUTRO_LAST),
            help="Shows the selected outro at the end of the video without extending the audio timeline.",
        )
        outro_duration = st.number_input(
            "End screen duration (seconds)",
            min_value=0.5,
            max_value=20.0,
            value=float(config.OUTRO_DURATION_SECONDS),
            step=0.5,
            disabled=not outro_last,
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
        "cover_first": bool(cover_first),
        "cover_duration": float(cover_duration),
        "outro_last": bool(outro_last),
        "outro_duration": float(outro_duration),
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
        input_root = st.text_input("Input root", value="input")
        output_dir = st.text_input("Output directory", value="output")

        st.header(SidebarSection.RENDER)
        render_modes = ["static", "slideshow"]
        mode = st.radio(
            "Mode",
            options=render_modes,
            index=_option_index(render_modes, config.DEFAULT_RENDER_MODE, default=1),
            horizontal=True,
        )
        aspect_options = ["9x16", "16x9"]
        aspect = st.selectbox(
            "Aspect",
            options=aspect_options,
            index=_option_index(aspect_options, config.DEFAULT_ASPECT, default=1),
        )
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

        _render_dependency_diagnostics(provider_descriptor, provider_values)

    return {
        **provider_values,
        "input_root": input_root,
        "output_dir": output_dir,
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
