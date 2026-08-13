from __future__ import annotations

import os
import sys
from typing import Literal

from video.encoding_profiles import PROFILE_AUTO, resolve_encoding_profile
from video.runtime_tools import (
    DEFAULT_WINDOWS_FFMPEG,
    DEFAULT_WINDOWS_FFPROBE,
    resolve_tool_path,
)

AspectRatio = Literal["9x16", "16x9"]

ASPECT_RESOLUTIONS: dict[AspectRatio, tuple[int, int]] = {
    "9x16": (2160, 3840),
    "16x9": (3840, 2160),
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

ZONE_IMAGE_SEQUENCE: list[str] = [
    "greeting", "opening", "introduction", "development",
    "climax", "falling", "ending", "farewell",
]

# Cards participate in slideshow ordering, but they are not story zones.
CARD_IMAGE_SEQUENCE: tuple[str, ...] = ("intro_card", "outro_card")
SLIDESHOW_IMAGE_SEQUENCE: tuple[str, ...] = (
    "intro_card",
    *ZONE_IMAGE_SEQUENCE,
    "outro_card",
)


ZONE_IMAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "intro_card": (
        "intro",   
        "intro_card",     
        "mo_dau",
        "mo-dau",
    ),
    "greeting": (
        "greeting", 
        "greeting_zone", 
        "loi_chao", 
        "loi-chao", 
    ),
    "opening": (
        "opening",           
        "opening_zone",
        "mo_truyen",
        "mo-truyen",
    ),
    "introduction": (
        "introduction", 
        "introduction_zone", 
        "gioi_thieu", 
        "gioi-thieu",
    ),
    "development": (
        "development", 
        "development_zone", 
        "trien_khai", 
        "trien-khai",
    ),
    "climax": (
        "climax", 
        "climax_zone", 
        "cao_trao", 
        "cao-trao",
    ),
    "falling": (
        "falling", 
        "falling_zone", 
        "ha_man", 
        "ha-man"
    ),
    "ending": (
        "ending", 
        "ending_zone",        
        "ket_truyen", 
        "ket-truyen",
    ),
    "farewell": (
        "farewell", 
        "farewell_zone", 
        "tam_biet", 
        "tam-biet",
    ),
    "outro_card": (
        "outro",  
        "outro_card",
        "closing",
        "phan_ket",
        "phan-ket",
    ),
}

DEFAULT_VIDEO_CODEC = os.getenv("VIDEO_CODEC", "libx264")
DEFAULT_AUDIO_CODEC = os.getenv("AUDIO_CODEC", "aac")
DEFAULT_AUDIO_BITRATE = os.getenv("AUDIO_BITRATE", "192k")
DEFAULT_PRESET = os.getenv("VIDEO_PRESET", "medium")
DEFAULT_CRF = int(os.getenv("VIDEO_CRF", "20"))
DEFAULT_FPS = int(os.getenv("VIDEO_FPS", "30"))
DEFAULT_TUNE_STILLIMAGE = os.getenv("VIDEO_TUNE", "stillimage")
DEFAULT_MOVFLAGS = os.getenv("VIDEO_MOVFLAGS", "+faststart")
DEFAULT_ENCODING_PROFILE = os.getenv("VIDEO_ENCODING_PROFILE", PROFILE_AUTO)
DEFAULT_LOUDNESS_PROFILE = os.getenv("VIDEO_LOUDNESS_PROFILE", "narration")
DEFAULT_QUALITY_GATE = os.getenv("VIDEO_QUALITY_GATE", "1").strip().lower() not in {"0", "false", "no"}
DEFAULT_PIXEL_FORMAT = os.getenv("VIDEO_PIXEL_FORMAT", "yuv420p")
DEFAULT_COLOR_PRIMARIES = os.getenv("VIDEO_COLOR_PRIMARIES", "bt709")
DEFAULT_COLOR_TRANSFER = os.getenv("VIDEO_COLOR_TRANSFER", "bt709")
DEFAULT_COLOR_SPACE = os.getenv("VIDEO_COLOR_SPACE", "bt709")
DEFAULT_COLOR_RANGE = os.getenv("VIDEO_COLOR_RANGE", "tv")
DEFAULT_GOP_SECONDS = float(os.getenv("VIDEO_GOP_SECONDS", "2.0"))
DEFAULT_RENDER_MODE = os.getenv("VIDEO_RENDER_MODE", "slideshow").strip().lower()
DEFAULT_ASPECT = os.getenv("VIDEO_ASPECT", "16x9").strip().lower()
DEFAULT_SUBTITLE_FONT = os.getenv("SUB_FONT", "Arial").strip() or "Arial"
DEFAULT_SUBTITLE_FONT_SIZE = int(os.getenv("SUB_FONT_SIZE", "12"))
DEFAULT_SUBTITLE_TEXT_COLOR = os.getenv("SUB_TEXT_COLOR", "#FFFFFF")
DEFAULT_SUBTITLE_BACKGROUND_COLOR = os.getenv("SUB_BACKGROUND_COLOR", "#000000")
DEFAULT_SUBTITLE_BACKGROUND_OPACITY = int(os.getenv("SUB_BACKGROUND_OPACITY", "50"))

FFMPEG_LOGLEVEL = os.getenv("FFMPEG_LOGLEVEL", "warning").strip()
FFMPEG_STREAM_LOG = os.getenv("FFMPEG_STREAM_LOG", "0").strip() == "1"
FFMPEG_STATS = os.getenv("FFMPEG_STATS", "1").strip() == "1"

_show_progress_env = os.getenv("SHOW_PROGRESS", "").strip().lower()
if _show_progress_env in ("0", "false", "no"):
    SHOW_PROGRESS = False
elif _show_progress_env in ("1", "true", "yes"):
    SHOW_PROGRESS = True
else:
    SHOW_PROGRESS = sys.stderr.isatty()

STDERR_TAIL_LINES = int(os.getenv("STDERR_TAIL_LINES", "40"))
KEEP_CONCAT_LIST = os.getenv("KEEP_CONCAT_LIST", "0").strip() == "1"
SLIDESHOW_MATCH_AUDIO = os.getenv("SLIDESHOW_MATCH_AUDIO", "1").strip() == "1"
SLIDESHOW_ZONE_AWARE = os.getenv("SLIDESHOW_ZONE_AWARE", "1").strip() == "1"
SLIDESHOW_COVER_FIRST = os.getenv("SLIDESHOW_COVER_FIRST", "1").strip().lower() not in {"0", "false", "no"}
COVER_DURATION_SECONDS = float(os.getenv("COVER_DURATION_SECONDS", "3.0"))
SLIDESHOW_OUTRO_LAST = os.getenv("SLIDESHOW_OUTRO_LAST", "1").strip().lower() not in {"0", "false", "no"}
OUTRO_DURATION_SECONDS = float(os.getenv("OUTRO_DURATION_SECONDS", "5.0"))
AUDIO_MATCH_EPSILON = float(os.getenv("AUDIO_MATCH_EPSILON", "0.2"))
PRINT_FFMPEG_VERSION = os.getenv("PRINT_FFMPEG_VERSION", "0").strip() == "1"


def get_output_resolution(aspect: AspectRatio) -> tuple[int, int]:
    profile = resolve_encoding_profile(DEFAULT_ENCODING_PROFILE, aspect)
    return profile.width, profile.height


def get_ffmpeg_exe() -> str:
    return resolve_tool_path("FFMPEG_EXE", "ffmpeg", DEFAULT_WINDOWS_FFMPEG)


def get_ffprobe_exe() -> str:
    return resolve_tool_path("FFPROBE_EXE", "ffprobe", DEFAULT_WINDOWS_FFPROBE)


FFMPEG_EXE = get_ffmpeg_exe()
FFPROBE_EXE = get_ffprobe_exe()
