from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class AudioStoryError(Exception):
    """Base exception for render-audio failures."""

    code = "audio_story_error"


class ConfigError(AudioStoryError):
    code = "config_error"


class ValidationError(AudioStoryError):
    code = "validation_error"


class RenderError(AudioStoryError):
    code = "render_error"


class DependencyError(ConfigError):
    code = "dependency_error"


class RuntimePathError(ConfigError):
    code = "runtime_path_error"


class AssetProfileError(ConfigError):
    code = "asset_profile_error"


class BgmConfigError(ConfigError):
    code = "bgm_config_error"


class TtsError(RenderError):
    code = "tts_error"


class UnsupportedTtsProviderError(TtsError, ConfigError):
    code = "unsupported_tts_provider_error"


class TtsDependencyError(TtsError, DependencyError):
    code = "tts_dependency_error"


class TtsNetworkError(TtsError):
    code = "tts_network_error"


class TtsRateLimitError(TtsNetworkError):
    code = "tts_rate_limit_error"


class TtsAuthenticationError(TtsError):
    code = "tts_authentication_error"


class TtsFallbackError(TtsError):
    code = "tts_fallback_error"


class FfmpegError(RenderError):
    code = "ffmpeg_error"


class FfmpegDependencyError(FfmpegError, DependencyError):
    code = "ffmpeg_dependency_error"


@dataclass(frozen=True)
class FailureContext:
    stage: str
    input_path: Optional[Path] = None
    output_dir: Optional[Path] = None
    profile_dir: Optional[Path] = None


__all__ = [
    "AssetProfileError",
    "AudioStoryError",
    "BgmConfigError",
    "ConfigError",
    "DependencyError",
    "FailureContext",
    "FfmpegDependencyError",
    "FfmpegError",
    "RenderError",
    "RuntimePathError",
    "TtsAuthenticationError",
    "TtsDependencyError",
    "UnsupportedTtsProviderError",
    "TtsError",
    "TtsFallbackError",
    "TtsNetworkError",
    "TtsRateLimitError",
    "ValidationError",
]
