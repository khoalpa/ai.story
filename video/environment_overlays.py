from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable

from video.story_environments import CANONICAL_STORY_ENVIRONMENTS
from video.subtitle_fonts import BUNDLED_FONT_FILES
from video.zone_timeline import (
    load_timeline_script,
    match_script_to_srt,
    normalize_zone,
    parse_srt,
)

logger = logging.getLogger(__name__)

ENVIRONMENT_WHITELIST = CANONICAL_STORY_ENVIRONMENTS


@dataclass(frozen=True)
class OverlayProfile:
    family: str
    opacity_percent: float
    temperature: str = "neutral"
    grain: float = 0.0
    vignette: float = 0.0
    light_leak: bool = False


OVERLAY_PROFILES: dict[str, OverlayProfile] = {
    "none": OverlayProfile("none", 0),
    "rain_soft": OverlayProfile("rain", 18, "cool", grain=14),
    "cafe_soft": OverlayProfile("bokeh", 8, "warm", grain=3, light_leak=True),
    "night_city_soft": OverlayProfile("light_streak", 10, "cool", grain=5, vignette=0.12),
    "forest_deep_ambience": OverlayProfile("dust_haze", 10, "green", grain=7),
    "school_hallway": OverlayProfile("dust", 5, "warm", grain=4),
    "garden_morning": OverlayProfile("pollen", 8, "warm", grain=6, light_leak=True),
    "bedroom_warm": OverlayProfile("dust", 5, "warm", grain=3, light_leak=True),
    "office_evening": OverlayProfile("bokeh", 4, "neutral", grain=2),
    "apartment_night": OverlayProfile("window_light", 5, "cool", grain=2),
    "train_night": OverlayProfile("light_streak", 12, "cool", grain=8, vignette=0.10),
    "sea_wind_soft": OverlayProfile("haze", 7, "cool", grain=4),
    "hospital_corridor_soft": OverlayProfile("haze", 3, "cool"),
    "old_house_ambience": OverlayProfile("dust", 10, "warm", grain=8, vignette=0.15),
    "library_soft": OverlayProfile("dust", 7, "warm", grain=5),
    "radio_studio_soft": OverlayProfile("led_bokeh", 5, "cool", grain=2),
    "kitchen_evening": OverlayProfile("steam", 7, "warm", grain=3),
    "street_after_rain": OverlayProfile("wet_bokeh", 10, "cool", grain=7, vignette=0.08),
    "rooftop_wind_soft": OverlayProfile("moving_haze", 7, "cool", grain=4),
    "river_soft": OverlayProfile("water_reflection", 8, "cool", grain=3),
}

INTENSITY_MULTIPLIERS = {"subtle": 0.65, "normal": 1.0, "cinematic": 1.35}


@dataclass(frozen=True)
class EnvironmentSegment:
    environment: str
    start: float
    end: float
    zone: str | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def normalize_environment(value: object) -> str:
    key = "" if value is None else str(value).strip().casefold()
    if not key:
        return "none"
    if key not in OVERLAY_PROFILES:
        logger.warning("Unknown story environment %r; using none.", value)
        return "none"
    return key


def build_environment_segments(
    *,
    timeline_json,
    subtitle,
    suppress_before: float = 0.0,
    suppress_after: float | None = None,
    minimum_duration: float = 1.5,
    bridge_gap: float = 1.5,
) -> list[EnvironmentSegment]:
    """Map story environments to real SRT time and merge adjacent equal profiles."""
    pairs = match_script_to_srt(load_timeline_script(timeline_json), parse_srt(subtitle))
    raw: list[EnvironmentSegment] = []
    for item, entry in pairs:
        environment = normalize_environment(item.get("environment"))
        start = max(float(entry.start), float(suppress_before))
        end = float(entry.end)
        if suppress_after is not None:
            end = min(end, float(suppress_after))
        if environment == "none" or end <= start:
            continue
        raw.append(EnvironmentSegment(environment, start, end, normalize_zone(item.get("zone"))))

    merged: list[EnvironmentSegment] = []
    for segment in sorted(raw, key=lambda item: (item.start, item.end)):
        if (
            merged
            and merged[-1].environment == segment.environment
            and segment.start <= merged[-1].end + max(0.0, bridge_gap)
        ):
            previous = merged[-1]
            merged[-1] = EnvironmentSegment(
                previous.environment,
                previous.start,
                max(previous.end, segment.end),
                previous.zone if previous.zone == segment.zone else None,
            )
        else:
            merged.append(segment)
    return [segment for segment in merged if segment.duration >= minimum_duration]


def _enable(segment: EnvironmentSegment) -> str:
    return f"between(t,{segment.start:.3f},{segment.end:.3f})"


def _moving_glyph(
    *,
    text: str,
    x: str,
    y: str,
    size: str,
    color: str,
    alpha: str,
    enable: str,
    blur: int = 0,
) -> str:
    escaped_text = text.replace("'", r"\'").replace(":", r"\:")
    font_path = str(BUNDLED_FONT_FILES["Patrick Hand"].resolve()).replace("\\", "/")
    font_path = font_path.replace(":", r"\:").replace("'", r"\'")
    shadow = f":shadowcolor={color}@0.12:shadowx={blur}:shadowy={blur}" if blur else ""
    return (
        f"drawtext=fontfile='{font_path}':text='{escaped_text}':x='{x}':y='{y}':"
        f"fontsize='{size}':fontcolor={color}{shadow}:alpha='{alpha}':enable='{enable}'"
    )


def _alpha_expression(segment: EnvironmentSegment, fade_seconds: float, opacity: float) -> str:
    fade = min(max(0.0, fade_seconds), segment.duration / 2.0)
    if fade <= 0:
        return f"{opacity:.3f}"
    return (
        f"{opacity:.3f}*min(1\\,(t-{segment.start:.3f})/{fade:.3f})*"
        f"min(1\\,({segment.end:.3f}-t)/{fade:.3f})"
    )


def _particle_filters(
    profile: OverlayProfile,
    segment: EnvironmentSegment,
    multiplier: float,
    fade_seconds: float,
    density_scale: float,
) -> list[str]:
    """Generate visible, deterministic motion without external overlay assets."""
    enable = _enable(segment)
    opacity = min(0.32, profile.opacity_percent * multiplier / 100.0)
    alpha = _alpha_expression(segment, fade_seconds, opacity)
    family = profile.family
    filters: list[str] = []

    if family in {"rain", "wet_bokeh"}:
        count = max(14, round(22 * multiplier * density_scale))
        for index in range(count):
            x_seed = 83 + index * 173
            y_seed = 41 + index * 257
            speed = 780 + (index % 4) * 135
            filters.append(
                _moving_glyph(
                    text="/",
                    x=f"mod({x_seed}+t*{-55 - index % 3 * 18}\\,w+120)-60",
                    y=f"mod({y_seed}+t*{speed}\\,h+180)-90",
                    size="max(24,h/30)",
                    color="white",
                    alpha=alpha,
                    enable=enable,
                    blur=1,
                )
            )

    if family in {"dust", "dust_haze", "pollen"}:
        count = max(10, round(16 * multiplier * density_scale))
        particle_color = "0xffe7ad" if family == "pollen" else "0xfff1d2"
        for index in range(count):
            filters.append(
                _moving_glyph(
                    text=".",
                    x=f"mod({97 + index * 211}+t*{13 + index % 4 * 5}\\,w+40)-20",
                    y=f"h*{(13 + index * 9) % 91}/100+sin(t*{0.35 + index % 3 * 0.11}+{index})*h/28",
                    size=f"max(16,h/{72 - index % 4 * 8})",
                    color=particle_color,
                    alpha=_alpha_expression(segment, fade_seconds, min(0.38, opacity * 1.25)),
                    enable=enable,
                    blur=2,
                )
            )

    if family in {"bokeh", "led_bokeh", "wet_bokeh", "window_light"}:
        colors = ("0xffba72", "0x8ed6ff", "0xffefbd")
        count = max(5, round(7 * multiplier * density_scale))
        for index in range(count):
            filters.append(
                _moving_glyph(
                    text="o",
                    x=f"mod({151 + index * 397}+t*{9 + index * 3}\\,w+160)-80",
                    y=f"h*{18 + index * 19}/100+sin(t*.22+{index})*h/24",
                    size=f"max(36,h/{19 + index % 4 * 3})",
                    color=colors[index % len(colors)],
                    alpha=_alpha_expression(segment, fade_seconds, min(0.20, opacity)),
                    enable=enable,
                    blur=4,
                )
            )

    if family in {"light_streak", "window_light"}:
        for index in range(max(4, round(5 * multiplier * density_scale))):
            filters.append(
                _moving_glyph(
                    text="--",
                    x=f"mod({index * 503}-t*{150 + index * 35}\\,w+500)-250",
                    y=f"h*{25 + index * 23}/100",
                    size="max(28,h/42)",
                    color="0xffd38a",
                    alpha=_alpha_expression(segment, fade_seconds, min(0.24, opacity)),
                    enable=enable,
                    blur=3,
                )
            )

    if family in {"haze", "steam", "moving_haze"}:
        filters.append(f"gblur=sigma={0.45 * multiplier:.3f}:enable='{enable}'")
        for index in range(max(5, round(7 * multiplier * density_scale))):
            filters.append(
                _moving_glyph(
                    text="~",
                    x=f"mod({index * 421}+t*{16 + index * 5}\\,w+240)-120",
                    y=f"mod({index * 293}-t*{20 + index * 4}\\,h+200)-100",
                    size="max(56,h/15)",
                    color="white",
                    alpha=_alpha_expression(segment, fade_seconds, min(0.12, opacity)),
                    enable=enable,
                    blur=6,
                )
            )

    if family == "water_reflection":
        for index in range(max(6, round(9 * multiplier * density_scale))):
            filters.append(
                _moving_glyph(
                    text="~~~",
                    x=f"mod({index * 317}+t*{18 + index * 3}\\,w+300)-150",
                    y=f"h*{58 + index * 8}/100",
                    size="max(28,h/38)",
                    color="0xbdeeff",
                    alpha=_alpha_expression(segment, fade_seconds, min(0.22, opacity)),
                    enable=enable,
                    blur=2,
                )
            )
    return filters


def build_environment_filter_chain(
    segments: Iterable[EnvironmentSegment],
    *,
    intensity: str = "normal",
    fade_seconds: float = 0.6,
    allow_lens_effects: bool = True,
    global_film_grain: float = 0.0,
    width: int = 1920,
    height: int = 1080,
) -> list[str]:
    """Return deterministic, asset-free FFmpeg filters for atmosphere overlays."""
    multiplier = INTENSITY_MULTIPLIERS.get(str(intensity).casefold(), 0.65)
    pixels = max(1, int(width)) * max(1, int(height))
    density_scale = min(2.5, max(0.75, math.sqrt(pixels / (1920 * 1080))))
    filters: list[str] = []
    for segment in segments:
        profile = OVERLAY_PROFILES[normalize_environment(segment.environment)]
        envelope = _enable(segment)
        filters.extend(
            _particle_filters(profile, segment, multiplier, fade_seconds, density_scale)
        )
        amount = min(20.0, profile.grain * multiplier)
        if amount > 0:
            filters.append(
                f"noise=alls={amount:.2f}:allf=t+u:enable='{envelope}'"
            )
        if profile.temperature == "warm":
            filters.append(f"colorbalance=rs=.025:bs=-.018:enable='{envelope}'")
        elif profile.temperature == "cool":
            filters.append(f"colorbalance=rs=-.018:bs=.025:enable='{envelope}'")
        elif profile.temperature == "green":
            filters.append(f"colorbalance=gs=.018:bs=-.010:enable='{envelope}'")
        if profile.vignette > 0:
            filters.append(f"vignette=angle=PI/{max(3.5, 8.0 / (profile.vignette * multiplier)):.2f}:enable='{envelope}'")
        if allow_lens_effects and profile.light_leak:
            alpha = min(0.10, profile.opacity_percent * multiplier / 180.0)
            filters.append(
                "drawbox=x=0:y=0:w=iw*.18:h=ih:"
                f"color=0xffb36b@{alpha:.3f}:t=fill:enable='{envelope}'"
            )
    if global_film_grain > 0:
        filters.append(f"noise=alls={min(12.0, float(global_film_grain)):.2f}:allf=t+u")
    return filters
