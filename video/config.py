from __future__ import annotations

import os
import sys
from typing import Literal

from common.image_sequence import ZONE_IMAGE_SEQUENCE
from video.paths import default_profile_root
from video.runtime_tools import (
    DEFAULT_WINDOWS_FFMPEG,
    DEFAULT_WINDOWS_FFPROBE,
    resolve_tool_path,
)

AspectRatio = Literal["9x16", "16x9"]

ASPECT_RESOLUTIONS: dict[AspectRatio, tuple[int, int]] = {
    "9x16": (1080, 1920),
    "16x9": (1920, 1080),
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


ZONE_IMAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "intro_card": (
        "intro_card",
        "intro-cover",
        "intro_cover",
        "opening",
        "opening_card",
        "prelude",
        "cover",
    ),
    "greeting": ("greeting", "loi_chao", "loi-chao", "hello"),
    "opening": (
        "zone_opening",
        "story_opening",
        "mo_truyen",
        "mo-truyen",
        "zone_intro",
        "story_intro",
        "opening",
    ),
    "introduction": ("introduction", "gioi_thieu", "gioi-thieu"),
    "development": ("development", "trien_khai", "trien-khai"),
    "climax": ("climax", "cao_trao", "cao-trao"),
    "falling": ("falling", "ha_man", "ha-man"),
    "ending": ("ending", "ket_truyen", "ket-truyen"),
    "farewell": ("farewell", "tam_biet", "tam-biet"),
    "outro_card": (
        "outro_card",
        "outro",
        "ending_card",
        "closing",
        "closing_card",
        "endcard",
        "credits",
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
AUDIO_MATCH_EPSILON = float(os.getenv("AUDIO_MATCH_EPSILON", "0.2"))
PRINT_FFMPEG_VERSION = os.getenv("PRINT_FFMPEG_VERSION", "0").strip() == "1"
DEFAULT_PROFILE_ROOT = str(default_profile_root())


def get_ffmpeg_exe() -> str:
    return resolve_tool_path("FFMPEG_EXE", "ffmpeg", DEFAULT_WINDOWS_FFMPEG)


def get_ffprobe_exe() -> str:
    return resolve_tool_path("FFPROBE_EXE", "ffprobe", DEFAULT_WINDOWS_FFPROBE)


FFMPEG_EXE = get_ffmpeg_exe()
FFPROBE_EXE = get_ffprobe_exe()
