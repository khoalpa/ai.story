from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EncodingProfile:
    name: str
    width: int
    height: int
    video_codec: str = "libx264"
    preset: str = "slow"
    crf: int = 19
    fps: int = 30
    tune: str = "stillimage"
    pixel_format: str = "yuv420p"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    gop_seconds: float = 2.0


PROFILE_AUTO = "auto"
PROFILE_BALANCED = "balanced"
PROFILE_YOUTUBE_4K = "youtube_4k"
PROFILE_YOUTUBE_1080P = "youtube_1080p"
PROFILE_TIKTOK = "tiktok"
PROFILE_MASTER = "master"
PROFILE_MASTER_HEVC = "master_hevc"

PROFILE_CHOICES = (
    PROFILE_AUTO,
    PROFILE_BALANCED,
    PROFILE_YOUTUBE_4K,
    PROFILE_YOUTUBE_1080P,
    PROFILE_TIKTOK,
    PROFILE_MASTER,
    PROFILE_MASTER_HEVC,
)


def normalize_encoding_profile(value: object) -> str:
    normalized = str(value or PROFILE_AUTO).strip().lower()
    return normalized if normalized in PROFILE_CHOICES else PROFILE_AUTO


def resolve_encoding_profile(value: object, aspect: str) -> EncodingProfile:
    name = normalize_encoding_profile(value)
    if name == PROFILE_AUTO:
        name = PROFILE_TIKTOK if aspect == "9x16" else PROFILE_YOUTUBE_4K
    if name == PROFILE_TIKTOK:
        return EncodingProfile(name, 1080, 1920, crf=19, fps=30)
    if name == PROFILE_YOUTUBE_1080P:
        return EncodingProfile(name, 1920, 1080, crf=19, fps=24)
    if name == PROFILE_YOUTUBE_4K:
        return EncodingProfile(name, 3840, 2160, crf=19, fps=24)
    if name == PROFILE_MASTER:
        width, height = ((2160, 3840) if aspect == "9x16" else (3840, 2160))
        return EncodingProfile(name, width, height, preset="slow", crf=17, fps=30 if aspect == "9x16" else 24)
    if name == PROFILE_MASTER_HEVC:
        width, height = ((2160, 3840) if aspect == "9x16" else (3840, 2160))
        return EncodingProfile(
            name,
            width,
            height,
            video_codec="libx265",
            preset="slow",
            crf=18,
            fps=30 if aspect == "9x16" else 24,
            pixel_format="yuv420p10le",
        )
    width, height = ((1080, 1920) if aspect == "9x16" else (1920, 1080))
    return EncodingProfile(PROFILE_BALANCED, width, height, preset="medium", crf=20, fps=30 if aspect == "9x16" else 24)
