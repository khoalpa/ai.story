from __future__ import annotations

"""Project-specific exception hierarchy.

These types let GUI/CLI code distinguish between profile resolution problems,
runtime dependency failures, and ffmpeg execution errors while preserving
backward compatibility with broad builtins such as FileNotFoundError and
RuntimeError.
"""


class RenderVideoError(Exception):
    """Base exception for the render_video project."""


class ProfileError(RenderVideoError):
    """Base exception for asset profile discovery and manifest resolution."""


class ProfileNotFoundError(FileNotFoundError, ProfileError):
    """Raised when an asset profile or its manifest cannot be found."""


class ProfileManifestError(ProfileError):
    """Raised when an asset profile manifest exists but is invalid or unreadable."""


class RuntimeDependencyError(RuntimeError, RenderVideoError):
    """Raised when ffmpeg/ffprobe or another runtime dependency is unavailable."""


class FfmpegExecutionError(RuntimeError, RenderVideoError):
    """Raised when ffmpeg starts but does not complete successfully."""


# Backward-compatible aliases kept for older callers.
AudioStoryError = RenderVideoError
ConfigError = RuntimeDependencyError
ValidationError = ProfileError
RenderError = FfmpegExecutionError
