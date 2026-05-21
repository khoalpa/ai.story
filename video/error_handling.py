from __future__ import annotations

from video.exceptions import (
    FfmpegExecutionError,
    ProfileError,
    RuntimeDependencyError,
)

USER_FACING_EXCEPTIONS = (
    ProfileError,
    RuntimeDependencyError,
    FfmpegExecutionError,
    FileNotFoundError,
    ValueError,
    OSError,
)


def is_user_facing_exception(exc: Exception) -> bool:
    return isinstance(exc, USER_FACING_EXCEPTIONS)


def format_user_facing_error(exc: Exception) -> str:
    if isinstance(exc, RuntimeDependencyError):
        return f"Runtime environment error: {exc}"
    if isinstance(exc, ProfileError):
        return f"Asset profile error: {exc}"
    if isinstance(exc, FfmpegExecutionError):
        return f"ffmpeg render error: {exc}"
    if isinstance(exc, FileNotFoundError):
        return str(exc)
    if isinstance(exc, ValueError):
        return f"Invalid input value: {exc}"
    if isinstance(exc, OSError):
        return f"File system error: {exc}"
    return str(exc)


def format_unexpected_error(exc: Exception) -> str:
    return f"Unexpected error: {exc}"
