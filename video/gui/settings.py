from __future__ import annotations

import re
from html import escape
from typing import Any

import streamlit as st

from video import config
from video.encoding_profiles import PROFILE_CHOICES
from video.gui.diagnostics_blocks import render_runtime_diagnostics_block
from video.gui.sidebar_sections import SidebarSection
from video.providers.base import VideoProviderDescriptor
from video.providers.registry import (
    get_video_provider_descriptors,
    normalize_video_provider,
)
from video.runtime_tools import collect_runtime_diagnostics
from video.subtitle_filters import resolve_subtitle_alignment
from video.subtitle_fonts import FONT_CHOICES, font_choice_label, font_preview_css

_LOGLEVEL_OPTIONS = ["quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug", "trace"]
_SUBTITLE_POSITION_OPTIONS = ["bottom", "top"]
_SUBTITLE_ALIGNMENT_OPTIONS = ["left", "center", "right"]
_SUBTITLE_FONT_OPTIONS = list(FONT_CHOICES)


def build_subtitle_preview_html(
    *,
    aspect: str,
    show_subtitles: bool,
    position: str,
    font: str,
    font_size: int,
    text_color: str,
    text_opacity: int,
    outline: int,
    shadow: int,
    outline_color: str,
    outline_opacity: int,
    alignment: int | None,
    margin_l: float,
    margin_r: float,
    margin_v: float,
) -> str:
    """Build a compact, approximate preview of the libass subtitle placement."""
    aspect_ratio = "9 / 16" if aspect == "9x16" else "16 / 9"
    preview_width = "190px" if aspect == "9x16" else "100%"
    safe_font = escape(font if font in _SUBTITLE_FONT_OPTIONS else "Arial", quote=True)
    bundled_font_css = font_preview_css(font)

    def safe_color(value: str, fallback: str) -> str:
        normalized = str(value or "").strip()
        return normalized if re.fullmatch(r"#[0-9a-fA-F]{6}", normalized) else fallback

    safe_text_color = safe_color(text_color, "#FFFFFF")
    text_alpha = min(100, max(0, int(text_opacity))) / 100
    text_red, text_green, text_blue = (
        int(safe_text_color[index:index + 2], 16) for index in (1, 3, 5)
    )
    preview_text_color = f"rgba({text_red},{text_green},{text_blue},{text_alpha:.2f})"
    safe_outline_color = safe_color(outline_color, "#000000")
    opacity = min(100, max(0, int(outline_opacity))) / 100
    red, green, blue = (
        int(safe_outline_color[index:index + 2], 16) for index in (1, 3, 5)
    )
    stroke_color = f"rgba({red},{green},{blue},{opacity:.2f})"
    preview_font_size = min(44, max(10, round(int(font_size) * 1.25)))
    outline_px = min(5, max(0, round(int(outline) * 0.7)))
    shadow_px = min(8, max(0, round(int(shadow) * 0.8)))

    effective_alignment = resolve_subtitle_alignment(
        position,
        str(alignment) if alignment is not None else "",
        srt_compat=True,
    )
    horizontal = {1: "left", 5: "left", 9: "left", 3: "right", 7: "right", 11: "right"}.get(
        effective_alignment, "center"
    )
    vertical = "bottom" if effective_alignment <= 3 else ("top" if effective_alignment <= 7 else "middle")
    vertical_style = (
        f"top:{margin_v}%;"
        if vertical == "top"
        else "top:50%;transform:translateY(-50%);"
        if vertical == "middle"
        else f"bottom:{margin_v}%;"
    )
    shadows: list[str] = []
    if outline_px:
        shadows.extend([
            f"-{outline_px}px 0 {stroke_color}", f"{outline_px}px 0 {stroke_color}",
            f"0 -{outline_px}px {stroke_color}", f"0 {outline_px}px {stroke_color}",
        ])
    if shadow_px:
        shadows.append(f"{shadow_px}px {shadow_px}px rgba(0,0,0,.65)")
    text_shadow = ",".join(shadows) if shadows else "none"
    visibility = "visible" if show_subtitles else "hidden"
    status = (
        f"Alignment {effective_alignment} · {vertical} · margin {margin_v:g}%"
        if show_subtitles else "Subtitles hidden"
    )

    return f"""
<div id="video-subtitle-preview">
  <style>
    {bundled_font_css}
    #video-subtitle-preview {{ margin: .75rem 0 .25rem; }}
    #video-subtitle-preview .vsp-head {{ display:flex;justify-content:space-between;gap:.5rem;margin-bottom:.4rem;font-size:.78rem;color:#6b7280; }}
    #video-subtitle-preview .vsp-frame {{ position:relative;width:{preview_width};max-width:100%;margin:auto;aspect-ratio:{aspect_ratio};overflow:hidden;border-radius:.55rem;background:linear-gradient(145deg,#173f58,#3e727c 52%,#d18a58);box-shadow:0 8px 22px rgba(0,0,0,.18); }}
    #video-subtitle-preview .vsp-frame:before {{ content:"";position:absolute;inset:0;background:radial-gradient(circle at 72% 25%,rgba(255,224,166,.8),transparent 18%),linear-gradient(to top,rgba(0,0,0,.35),transparent 45%); }}
    #video-subtitle-preview .vsp-hills {{ position:absolute;left:-8%;right:-8%;bottom:-3%;height:46%;background:linear-gradient(155deg,transparent 8%,#183c37 9% 35%,#255c4c 36% 58%,#102b29 59%);opacity:.9; }}
    #video-subtitle-preview .vsp-safe {{ position:absolute;inset:5%;border:1px dashed rgba(255,255,255,.45);border-radius:.2rem; }}
    #video-subtitle-preview .vsp-text {{ position:absolute;z-index:2;left:{margin_l}%;right:{margin_r}%;{vertical_style}visibility:{visibility};text-align:{horizontal};color:{preview_text_color};font-family:'{safe_font}',sans-serif;font-size:{preview_font_size}px;font-weight:600;line-height:1.25;text-shadow:{text_shadow};overflow-wrap:anywhere; }}
  </style>
  <div class="vsp-head"><strong>Live preview</strong><span>{escape(status)}</span></div>
  <div class="vsp-frame" role="img" aria-label="Subtitle position preview for {escape(aspect)} video">
    <div class="vsp-hills"></div><div class="vsp-safe"></div>
    <div class="vsp-text">Đây là nội dung subtitle mẫu trên video</div>
  </div>
</div>
"""


def _render_dependency_diagnostics(provider: VideoProviderDescriptor, settings: dict[str, Any]) -> None:
    collector = provider.collect_runtime_diagnostics
    report = collector(settings) if collector is not None else collect_runtime_diagnostics()
    render_runtime_diagnostics_block(report, expanded=False, serializer=lambda info: info.as_dict())


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


def default_subtitle_font_size(mode: str, aspect: str) -> int:
    return 8 if mode == "slideshow" and aspect == "9x16" else 12


def default_subtitle_position(mode: str, aspect: str) -> str:
    return "top" if mode == "slideshow" and aspect == "9x16" else "bottom"


def subtitle_alignment_value(alignment: str) -> int:
    return {"left": 1, "center": 2, "right": 3}.get(str(alignment).lower(), 2)


def should_update_subtitle_position(
    *, mode: str, current: str, suggested: str, previous_suggestion: str
) -> bool:
    return (
        mode == "slideshow"
        and current in {"", previous_suggestion, "top", "bottom"}
        and current != suggested
    )


def should_update_subtitle_font_size(
    *, mode: str, current: int, suggested: int, previous_suggestion: int
) -> bool:
    return (
        mode == "slideshow"
        and current in {previous_suggestion, 8, 12}
        and current != suggested
    )


def _sync_subtitle_font_size_default(mode: str, aspect: str) -> None:
    suggested = default_subtitle_font_size(mode, aspect)
    previous = int(st.session_state.get("video_auto_subtitle_font_size", 12))
    current = int(st.session_state.get("subtitle_font_size", suggested))
    if should_update_subtitle_font_size(
        mode=mode,
        current=current,
        suggested=suggested,
        previous_suggestion=previous,
    ):
        st.session_state["subtitle_font_size"] = suggested
    else:
        st.session_state.setdefault("subtitle_font_size", suggested)
    st.session_state["video_auto_subtitle_font_size"] = suggested


def _sync_subtitle_position_default(mode: str, aspect: str) -> None:
    suggested = default_subtitle_position(mode, aspect)
    previous = str(st.session_state.get("video_auto_subtitle_position") or "bottom")
    current = str(st.session_state.get("subtitle_position") or suggested)
    if should_update_subtitle_position(
        mode=mode,
        current=current,
        suggested=suggested,
        previous_suggestion=previous,
    ):
        st.session_state["subtitle_position"] = suggested
    else:
        st.session_state.setdefault("subtitle_position", suggested)
    st.session_state["video_auto_subtitle_position"] = suggested


def _render_subtitle_style_settings(mode: str, aspect: str) -> dict[str, Any]:
    _sync_subtitle_font_size_default(mode, aspect)
    _sync_subtitle_position_default(mode, aspect)
    with st.expander("Subtitle styling", expanded=False):
        show_subtitles = st.checkbox(
            "Show subtitles on video",
            value=True,
            help="Disable this to render the video without burning subtitle text into its frames.",
        )
        st.markdown("**Placement**")
        subtitle_position = st.selectbox(
            "Subtitle position",
            options=_SUBTITLE_POSITION_OPTIONS,
            key="subtitle_position",
            disabled=not show_subtitles,
        )
        subtitle_alignment_choice = st.selectbox(
            "Alignment",
            options=_SUBTITLE_ALIGNMENT_OPTIONS,
            index=_SUBTITLE_ALIGNMENT_OPTIONS.index("center"),
            help="Controls horizontal alignment. Subtitle position independently controls top or bottom.",
            disabled=not show_subtitles,
        )
        subtitle_margin_v = st.number_input(
            "Vertical margin (%)",
            min_value=0.0,
            max_value=50.0,
            value=3.0 if aspect == "9x16" else 2.0,
            step=0.5,
            help="Distance from the selected top or bottom edge.",
            disabled=not show_subtitles,
        )
        subtitle_margin_horizontal = st.number_input(
            "Horizontal safe margin (%)",
            min_value=0.0,
            max_value=50.0,
            value=4.0,
            step=0.5,
            help="Equal safe-area margin on the left and right edges.",
            disabled=not show_subtitles,
        )

        st.markdown("**Typography**")
        subtitle_font_size = st.number_input(
            "Subtitle font size",
            min_value=1,
            max_value=200,
            step=1,
            key="subtitle_font_size",
            disabled=not show_subtitles,
        )
        default_background_opacity = max(
            0,
            min(100, int(config.DEFAULT_SUBTITLE_BACKGROUND_OPACITY)),
        )
        subtitle_font = st.selectbox(
            "Subtitle font",
            options=_SUBTITLE_FONT_OPTIONS,
            index=_option_index(_SUBTITLE_FONT_OPTIONS, config.DEFAULT_SUBTITLE_FONT),
            help="Vietnamese handwriting and artistic fonts are bundled; standard fonts use the local system.",
            format_func=font_choice_label,
            disabled=not show_subtitles,
        )
        text_color_column, text_opacity_column = st.columns(2)
        with text_color_column:
            subtitle_text_color = st.color_picker(
                "Subtitle text color",
                value=str(config.DEFAULT_SUBTITLE_TEXT_COLOR),
                disabled=not show_subtitles,
            )
        with text_opacity_column:
            subtitle_text_opacity = st.slider(
                "Text opacity (%)", min_value=0, max_value=100, value=100,
                disabled=not show_subtitles,
            )

        st.markdown("**Readability**")
        subtitle_outline = st.number_input(
            "Outline size", min_value=0, max_value=20, value=1, step=1,
            disabled=not show_subtitles,
        )
        background_color_column, background_opacity_column = st.columns(2)
        with background_color_column:
            subtitle_background_color = st.color_picker(
                "Subtitle outline color",
                value=str(config.DEFAULT_SUBTITLE_BACKGROUND_COLOR),
                disabled=not show_subtitles,
            )
        with background_opacity_column:
            subtitle_background_opacity = st.slider(
                "Outline opacity (%)",
                min_value=0,
                max_value=100,
                value=default_background_opacity,
                help="Controls the outline around each glyph. Set to 0% for a transparent outline.",
                disabled=not show_subtitles,
            )
        subtitle_alignment = subtitle_alignment_value(subtitle_alignment_choice)
        st.markdown(
            build_subtitle_preview_html(
                aspect=aspect,
                show_subtitles=bool(show_subtitles),
                position=subtitle_position,
                font=subtitle_font,
                font_size=int(subtitle_font_size),
                text_color=subtitle_text_color,
                text_opacity=int(subtitle_text_opacity),
                outline=int(subtitle_outline),
                shadow=0,
                outline_color=subtitle_background_color,
                outline_opacity=int(subtitle_background_opacity),
                alignment=subtitle_alignment,
                margin_l=float(subtitle_margin_horizontal),
                margin_r=float(subtitle_margin_horizontal),
                margin_v=float(subtitle_margin_v),
            ),
            unsafe_allow_html=True,
        )
    return {
        "show_subtitles": bool(show_subtitles),
        "subtitle_position": subtitle_position,
        "subtitle_font": subtitle_font,
        "subtitle_font_size": int(subtitle_font_size),
        "subtitle_text_color": subtitle_text_color,
        "subtitle_text_opacity": int(subtitle_text_opacity),
        "subtitle_outline": int(subtitle_outline),
        "subtitle_shadow": 0,
        "subtitle_background_color": subtitle_background_color,
        "subtitle_background_opacity": int(subtitle_background_opacity),
        "subtitle_alignment": subtitle_alignment,
        "subtitle_margin_l": float(subtitle_margin_horizontal),
        "subtitle_margin_r": float(subtitle_margin_horizontal),
        "subtitle_margin_v": float(subtitle_margin_v),
        "subtitle_force_style": None,
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


def _render_environment_overlay_settings(mode: str) -> dict[str, Any]:
    with st.expander("Environment overlays", expanded=False):
        enabled = st.checkbox(
            "Use story environment overlays",
            value=bool(config.ENVIRONMENT_OVERLAYS_ENABLED),
            disabled=mode != "slideshow",
            help="Build subtle atmosphere effects from each story.json script item's environment field.",
        )
        intensity_options = ["subtle", "normal", "cinematic"]
        default_intensity = config.ENVIRONMENT_OVERLAY_INTENSITY
        intensity = st.selectbox(
            "Intensity",
            options=intensity_options,
            index=_option_index(intensity_options, default_intensity, default=1),
            disabled=not enabled or mode != "slideshow",
        )
        fade = st.number_input(
            "Overlay transition (seconds)",
            min_value=0.0,
            max_value=3.0,
            value=float(config.ENVIRONMENT_OVERLAY_FADE_SECONDS),
            step=0.1,
            disabled=not enabled or mode != "slideshow",
        )
        lens_effects = st.checkbox(
            "Allow light leaks and lens effects",
            value=bool(config.ENVIRONMENT_ALLOW_LENS_EFFECTS),
            disabled=not enabled or mode != "slideshow",
        )
        film_grain = st.number_input(
            "Global film grain",
            min_value=0.0,
            max_value=12.0,
            value=float(config.ENVIRONMENT_GLOBAL_FILM_GRAIN),
            step=0.5,
            disabled=not enabled or mode != "slideshow",
            help="0 disables global grain. Environment-specific grain remains controlled by Intensity.",
        )
        st.caption("Cover and outro are protected; unknown environments fall back to none.")
    return {
        "environment_overlays": bool(enabled),
        "environment_overlay_intensity": str(intensity),
        "environment_overlay_fade": float(fade),
        "environment_allow_lens_effects": bool(lens_effects),
        "environment_global_film_grain": float(film_grain),
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
        input_root = st.text_input("Input root", value="output")
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
            **_render_subtitle_style_settings(mode, aspect),
            **_render_slideshow_behavior_settings(),
            **_render_environment_overlay_settings(mode),
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
