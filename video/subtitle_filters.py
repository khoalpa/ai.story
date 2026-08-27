from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from video import config
from video.config import AspectRatio
from video.subtitle_fonts import bundled_fonts_dir

# FFmpeg's SRT-to-ASS conversion uses this virtual script resolution. ASS
# style margins must be expressed in these coordinates; libass then scales
# them to the actual output frame.
ASS_PLAY_RES_X = 384
ASS_PLAY_RES_Y = 288


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


def subtitle_text_color_to_ass(color: str, opacity: int | float = 100) -> str:
    """Convert #RRGGBB plus opacity percent to ASS &HAABBGGRR format."""
    return subtitle_background_to_ass(color, opacity)


def subtitle_margin_percent_to_ass_units(percent: int | float | str, play_res: int) -> int:
    """Convert a frame-relative margin percentage to ASS script units."""
    try:
        normalized = float(percent)
    except (TypeError, ValueError):
        normalized = 2.0
    normalized = min(50.0, max(0.0, normalized))
    return int(round(int(play_res) * normalized / 100.0))


def subtitle_play_resolution(subtitle: Path) -> tuple[int, int]:
    """Return the ASS script resolution, or FFmpeg's SRT conversion default."""
    if subtitle.suffix.lower() == ".ass" and subtitle.is_file():
        content = subtitle.read_text(encoding="utf-8-sig", errors="replace")
        x_match = re.search(r"(?im)^\s*PlayResX\s*:\s*(\d+)\s*$", content)
        y_match = re.search(r"(?im)^\s*PlayResY\s*:\s*(\d+)\s*$", content)
        if x_match and y_match:
            play_res_x = int(x_match.group(1))
            play_res_y = int(y_match.group(1))
            if play_res_x > 0 and play_res_y > 0:
                return play_res_x, play_res_y
    return ASS_PLAY_RES_X, ASS_PLAY_RES_Y


def resolve_subtitle_alignment(
    position: str,
    alignment_override: str = "",
    *,
    srt_compat: bool = False,
) -> int:
    """Resolve vertical/horizontal alignment for ASS or FFmpeg-converted SRT.

    FFmpeg's SRT reader exposes the generated style with legacy SSA alignment
    numbering (top-center is 6), while native ASS uses numpad numbering
    (top-center is 8).  Mixing the two is what placed portrait SRT text near
    the middle of the frame even though the UI selected ``top``.
    """
    normalized_position = str(position or "bottom").strip().lower()
    try:
        requested = int(str(alignment_override or "").strip())
    except ValueError:
        requested = 2
    horizontal_column = ((requested - 1) % 3) + 1 if 1 <= requested <= 9 else 2
    if srt_compat:
        if normalized_position in {"top", "upper"}:
            return 4 + horizontal_column
        if normalized_position in {"middle", "center", "mid"}:
            return 8 + horizontal_column
        return horizontal_column
    row_base = 6 if normalized_position in {"top", "upper"} else (
        3 if normalized_position in {"middle", "center", "mid"} else 0
    )
    return row_base + horizontal_column


def apply_authoritative_subtitle_placement(
    force_style: str,
    *,
    alignment: int,
    margin_l: int,
    margin_r: int,
    margin_v: int,
) -> str:
    """Merge a custom ASS style without letting it override GUI placement controls."""
    placement_keys = {"alignment", "marginl", "marginr", "marginv"}
    declarations = []
    for declaration in str(force_style or "").split(","):
        key, separator, _value = declaration.partition("=")
        if separator and key.strip().lower() in placement_keys:
            continue
        if declaration.strip():
            declarations.append(declaration.strip())
    declarations.extend(
        [
            f"Alignment={alignment}",
            f"MarginV={margin_v}",
            f"MarginL={margin_l}",
            f"MarginR={margin_r}",
        ]
    )
    return ",".join(declarations)


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
    pre_subtitle_filters: Optional[list[str]] = None,
) -> str:
    base = build_scale_pad_filter(aspect)
    if pre_subtitle_filters:
        base = ",".join((base, *pre_subtitle_filters))
    if subtitle is None:
        return base

    if pre_subtitle_fps and pre_subtitle_fps > 0:
        base = f"{base},fps={int(pre_subtitle_fps)}"

    subtitle_for_filter = str(subtitle).replace("\\", "/")
    sub_esc = escape_subtitle_path(subtitle_for_filter)

    sub_font = os.getenv("SUB_FONT", "Playwrite VN").strip() or "Playwrite VN"
    sub_fontsize = int(os.getenv("SUB_FONT_SIZE", "8"))
    sub_text_color = os.getenv("SUB_TEXT_COLOR", "#FFFFFF")
    sub_text_opacity = int(os.getenv("SUB_TEXT_OPACITY", "100"))
    sub_outline = int(os.getenv("SUB_OUTLINE", "1"))
    sub_shadow = int(os.getenv("SUB_SHADOW", "0"))
    sub_background_color = os.getenv("SUB_BACKGROUND_COLOR", "#000000")
    sub_background_opacity = int(os.getenv("SUB_BACKGROUND_OPACITY", "50"))
    sub_position = os.getenv("SUB_POSITION", "bottom").strip().lower()
    sub_alignment_override = os.getenv("SUB_ALIGNMENT", "").strip()

    default_fontsize = max(sub_fontsize, 8)

    sub_fontsize = int(os.getenv("SUB_FONT_SIZE", str(default_fontsize)))
    play_res_x, play_res_y = subtitle_play_resolution(subtitle)
    sub_margin_l = subtitle_margin_percent_to_ass_units(os.getenv("SUB_MARGIN_L", "2"), play_res_x)
    sub_margin_r = subtitle_margin_percent_to_ass_units(os.getenv("SUB_MARGIN_R", "2"), play_res_x)
    sub_margin_v = subtitle_margin_percent_to_ass_units(os.getenv("SUB_MARGIN_V", "2"), play_res_y)

    sub_alignment = resolve_subtitle_alignment(
        sub_position,
        sub_alignment_override,
        srt_compat=subtitle.suffix.lower() != ".ass",
    )

    outline_background = subtitle_background_to_ass(
        sub_background_color,
        sub_background_opacity,
    )
    primary_color = subtitle_text_color_to_ass(sub_text_color, sub_text_opacity)
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
    custom_force_style = os.getenv("SUB_FORCE_STYLE", "").strip()
    force_style = apply_authoritative_subtitle_placement(
        custom_force_style or force_style_default,
        alignment=sub_alignment,
        margin_l=sub_margin_l,
        margin_r=sub_margin_r,
        margin_v=sub_margin_v,
    ).replace("'", "\\'")
    output_width, output_height = config.get_output_resolution(aspect)
    fonts_dir = bundled_fonts_dir()
    fonts_dir_option = ""
    if fonts_dir is not None:
        fonts_dir_text = str(fonts_dir).replace("\\", "/")
        fonts_dir_option = f":fontsdir='{escape_subtitle_path(fonts_dir_text)}'"
    return (
        f"{base},subtitles='{sub_esc}':original_size={output_width}x{output_height}:"
        f"force_style='{force_style}'{fonts_dir_option}"
    )
