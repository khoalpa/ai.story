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
        return f"Lỗi môi trường chạy: {exc}"
    if isinstance(exc, ProfileError):
        return f"Lỗi asset profile: {exc}"
    if isinstance(exc, FfmpegExecutionError):
        return f"Lỗi ffmpeg khi render: {exc}"
    if isinstance(exc, FileNotFoundError):
        return str(exc)
    if isinstance(exc, ValueError):
        return f"Giá trị đầu vào không hợp lệ: {exc}"
    if isinstance(exc, OSError):
        return f"Lỗi hệ thống tệp: {exc}"
    return str(exc)


def format_unexpected_error(exc: Exception) -> str:
    return f"Lỗi không mong đợi: {exc}"
