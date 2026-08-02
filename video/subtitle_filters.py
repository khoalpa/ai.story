from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from video import config
from video.config import AspectRatio


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

    sub_fontsize = int(os.getenv("SUB_FONT_SIZE", "8"))
    sub_outline = int(os.getenv("SUB_OUTLINE", "2"))
    sub_shadow = int(os.getenv("SUB_SHADOW", "0"))
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

    force_style_default = (
        f"Fontsize={sub_fontsize},"
        f"Outline={sub_outline},"
        f"Shadow={sub_shadow},"
        "BorderStyle=3,"
        "BackColour=&H80000000,"
        "OutlineColour=&H00000000,"
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
