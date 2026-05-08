from __future__ import annotations

from video.providers.base import VideoProviderDescriptor, VideoProviderSettings
from video.providers.registry import (
    DEFAULT_VIDEO_PROVIDER,
    get_video_provider_choices,
    get_video_provider_descriptor,
    get_video_provider_descriptors,
    normalize_video_provider,
)

__all__ = [
    "DEFAULT_VIDEO_PROVIDER",
    "VideoProviderDescriptor",
    "VideoProviderSettings",
    "get_video_provider_choices",
    "get_video_provider_descriptor",
    "get_video_provider_descriptors",
    "normalize_video_provider",
]
