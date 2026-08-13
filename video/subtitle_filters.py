from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from video import config
from video.config import AspectRatio


def subtitle_background_to_ass(color: str, opacity: int | float) -> str:
    """Convert #RRGGBB plus opacity percent to ASS &HAABBGGRR format."""
    normalized = str(color or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", normalized):
        normalized = "#000000"
    opacity_percent = min(100.0, max(0.0, float(opacity)))
    alpha = round(255 * (1.0 - opacity_percent / 100.0))
    red = normalized[1:3]
    green = normalized[3:5]
    blue = normalized[5:7]
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


def subtitle_text_color_to_ass(color: str) -> str:
    """Convert #RRGGBB to the opaque ASS &HAABBGGRR color format."""
    return subtitle_background_to_ass(color, 100)


def escape_subtitle_path(path: Path | str) -> str:
    s = str(path)
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    return s


def build_scale_pad_filter(aspect: AspectRatio) -> str:
    w, h = config.get_output_resolution(aspect)
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format={config.DEFAULT_PIXEL_FORMAT},"
        "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )


def build_vf_filter(
    aspect: AspectRatio,
    subtitle: Optional[Path],
    *,
    pre_subtitle_fps: Optional[int] = None,
) -> str:
    base = build_scale_pad_filter(aspect)
    if subtitle is None:
        return base

    if pre_subtitle_fps and pre_subtitle_fps > 0:
        base = f"{base},fps={int(pre_subtitle_fps)}"

    subtitle_for_filter = str(subtitle).replace("\\", "/")
    sub_esc = escape_subtitle_path(subtitle_for_filter)

    sub_font = os.getenv("SUB_FONT", "Arial").strip() or "Arial"
    sub_fontsize = int(os.getenv("SUB_FONT_SIZE", "8"))
    sub_text_color = os.getenv("SUB_TEXT_COLOR", "#FFFFFF")
    sub_outline = int(os.getenv("SUB_OUTLINE", "2"))
    sub_shadow = int(os.getenv("SUB_SHADOW", "0"))
    sub_background_color = os.getenv("SUB_BACKGROUND_COLOR", "#000000")
    sub_background_opacity = int(os.getenv("SUB_BACKGROUND_OPACITY", "50"))
    sub_position = os.getenv("SUB_POSITION", "bottom").strip().lower()
    sub_alignment_override = os.getenv("SUB_ALIGNMENT", "").strip()

    if aspect == "9x16":
        default_fontsize = max(sub_fontsize, 8)
        default_margin_l = 40
        default_margin_r = 40
        if sub_position in ("top", "upper"):
            default_alignment = 8
            default_margin_v = 140
        elif sub_position in ("middle", "center", "mid"):
            default_alignment = 5
            default_margin_v = 0
        else:
            default_alignment = 2
            default_margin_v = 240
    else:
        default_fontsize = max(sub_fontsize, 8)
        default_margin_l = 60
        default_margin_r = 60
        if sub_position in ("top", "upper"):
            default_alignment = 8
            default_margin_v = 80
        elif sub_position in ("middle", "center", "mid"):
            default_alignment = 5
            default_margin_v = 0
        else:
            default_alignment = 2
            default_margin_v = 100

    sub_fontsize = int(os.getenv("SUB_FONT_SIZE", str(default_fontsize)))
    sub_margin_l = int(os.getenv("SUB_MARGIN_L", str(default_margin_l)))
    sub_margin_r = int(os.getenv("SUB_MARGIN_R", str(default_margin_r)))
    sub_margin_v = int(os.getenv("SUB_MARGIN_V", str(default_margin_v)))

    if sub_alignment_override:
        try:
            sub_alignment = int(sub_alignment_override)
        except ValueError:
            sub_alignment = default_alignment
    else:
        sub_alignment = default_alignment

    outline_background = subtitle_background_to_ass(
        sub_background_color,
        sub_background_opacity,
    )
    primary_color = subtitle_text_color_to_ass(sub_text_color)
    force_style_default = (
        f"FontName={sub_font},"
        f"Fontsize={sub_fontsize},"
        f"PrimaryColour={primary_color},"
        f"Outline={sub_outline},"
        f"Shadow={sub_shadow},"
        "BorderStyle=1,"
        f"BackColour={outline_background},"
        f"OutlineColour={outline_background},"
        "WrapStyle=0,"
        f"Alignment={sub_alignment},"
        f"MarginV={sub_margin_v},"
        f"MarginL={sub_margin_l},"
        f"MarginR={sub_margin_r}"
    )
    force_style = os.getenv("SUB_FORCE_STYLE", force_style_default).replace("'", "\\'")
    output_width, output_height = config.get_output_resolution(aspect)
    return (
        f"{base},subtitles='{sub_esc}':original_size={output_width}x{output_height}:"
        f"force_style='{force_style}'"
    )
