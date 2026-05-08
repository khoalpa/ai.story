from __future__ import annotations

from video.providers import (
    DEFAULT_VIDEO_PROVIDER,
    VideoProviderDescriptor,
    VideoProviderSettings,
    get_video_provider_choices,
    get_video_provider_descriptor,
    get_video_provider_descriptors,
    normalize_video_provider,
)

VIDEO_PROVIDER_FFMPEG_LOCAL = "ffmpeg_local"
SUPPORTED_VIDEO_PROVIDERS = tuple(get_video_provider_choices())
VIDEO_PROVIDER_DESCRIPTORS: dict[str, VideoProviderDescriptor] = get_video_provider_descriptors()

__all__ = [
    "DEFAULT_VIDEO_PROVIDER",
    "SUPPORTED_VIDEO_PROVIDERS",
    "VIDEO_PROVIDER_DESCRIPTORS",
    "VIDEO_PROVIDER_FFMPEG_LOCAL",
    "VideoProviderDescriptor",
    "VideoProviderSettings",
    "get_video_provider_choices",
    "get_video_provider_descriptor",
    "get_video_provider_descriptors",
    "normalize_video_provider",
]
