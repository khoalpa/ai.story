from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from video.runtime_diagnostics import (
    RuntimeDiagnosticsReport,
    collect_runtime_diagnostics as _collect_runtime_diagnostics,
    describe_tool,
    read_tool_version,
    resolve_tool_path as resolve_runtime_tool_path,
)
from video.exceptions import RuntimeDependencyError
from video.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ok: bool
    version: str
    detail: str = ""


DEFAULT_WINDOWS_FFMPEG = Path(
    r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe"
)
DEFAULT_WINDOWS_FFPROBE = Path(
    r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffprobe.exe"
)


def resolve_tool_path(env_var: str, executable_name: str, windows_fallback: Path) -> str:
    import os

    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return env_value

    discovered = shutil.which(executable_name)
    if discovered:
        return discovered

    if platform.system().lower().startswith("win") and windows_fallback.is_file():
        logger.warning(
            "Using deprecated legacy fallback for %s: %s. Prefer PATH or %s.",
            executable_name,
            windows_fallback,
            env_var,
        )
        return str(windows_fallback)

    return executable_name


def is_available_tool(path_or_name: str) -> bool:
    return resolve_runtime_tool_path(path_or_name) is not None


def get_available_tool_path(path_or_name: str) -> Optional[str]:
    return resolve_runtime_tool_path(path_or_name)


def get_tool_version_line(path_or_name: str) -> Optional[str]:
    return read_tool_version(path_or_name)


def collect_runtime_diagnostics(
    ffmpeg_exe: Optional[str] = None,
    ffprobe_exe: Optional[str] = None,
) -> RuntimeDiagnosticsReport:
    ffmpeg_value = ffmpeg_exe or resolve_tool_path("FFMPEG_EXE", "ffmpeg", DEFAULT_WINDOWS_FFMPEG)
    ffprobe_value = ffprobe_exe or resolve_tool_path("FFPROBE_EXE", "ffprobe", DEFAULT_WINDOWS_FFPROBE)
    return _collect_runtime_diagnostics(
        tool_configs=(("ffmpeg", ffmpeg_value), ("ffprobe", ffprobe_value)),
        dependency_modules=("yaml", "requests", "streamlit"),
    )


def format_runtime_diagnostics(ffmpeg_exe: str, ffprobe_exe: str) -> str:
    return "\n".join(
        [
            f"ffmpeg:  {describe_tool(ffmpeg_exe)}",
            f"ffprobe: {describe_tool(ffprobe_exe)}",
        ]
    )


MISSING_FFMPEG_GUIDANCE = (
    "ffmpeg executable not found. Install ffmpeg, add it to PATH, "
    "or set the FFMPEG_EXE environment variable to the actual ffmpeg binary."
)


WARNING_FFPROBE_GUIDANCE = (
    "ffprobe executable not found. The project can still render, but duration "
    "detection will be less accurate. Install ffprobe or set FFPROBE_EXE if needed."
)


def ensure_tools(ffmpeg_exe: str, ffprobe_exe: str, *, print_ffmpeg_version: bool = False) -> None:
    ffmpeg_resolved = get_available_tool_path(ffmpeg_exe)
    ffprobe_resolved = get_available_tool_path(ffprobe_exe)

    if not ffmpeg_resolved:
        raise RuntimeDependencyError(f"{MISSING_FFMPEG_GUIDANCE}\nConfigured value: {ffmpeg_exe}")

    if not ffprobe_resolved:
        logger.warning("%s Configured value: %s", WARNING_FFPROBE_GUIDANCE, ffprobe_exe)

    logger.info("[Runtime tools]\n%s", format_runtime_diagnostics(ffmpeg_exe, ffprobe_exe))

    if print_ffmpeg_version:
        version = get_tool_version_line(ffmpeg_exe)
        if version:
            logger.info(version)
