from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Final

from audio.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_WINDOWS_FFMPEG: Final[Path] = Path(
    r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe"
)
DEFAULT_WINDOWS_FFPROBE: Final[Path] = Path(
    r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffprobe.exe"
)


def prefer_real_binary(path_or_name: str, windows_fallback: Path) -> str:
    """Replace a Chocolatey shim with its real binary when available."""

    raw = str(path_or_name or "").strip()
    if not raw:
        return raw
    candidate = Path(raw)
    if (
        platform.system().lower().startswith("win")
        and windows_fallback.is_file()
        and candidate.parent.name.lower() == "bin"
        and candidate.parent.parent.name.lower() == "chocolatey"
    ):
        logger.warning(
            "Configured executable is a Chocolatey shim (%s); using the real binary %s "
            "to avoid Windows Application Control blocking the shim.",
            candidate,
            windows_fallback,
        )
        return str(windows_fallback)
    return raw


def resolve_tool_path(env_var: str, executable_name: str, windows_fallback: Path) -> str:
    """Resolve binary path in order: ENV -> PATH -> existing legacy Windows fallback -> executable name.

    Returning ``executable_name`` as the final step keeps failure explicit later in runtime checks,
    instead of silently pinning to a nonexistent hard-coded path.
    """

    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return prefer_real_binary(env_value, windows_fallback)

    discovered = shutil.which(executable_name)
    if discovered:
        return prefer_real_binary(discovered, windows_fallback)

    if platform.system().lower().startswith("win") and windows_fallback.is_file():
        logger.warning(
            "Using deprecated legacy fallback for %s: %s. Prefer PATH or %s.",
            executable_name,
            windows_fallback,
            env_var,
        )
        return str(windows_fallback)

    return executable_name


def get_ffmpeg_exe() -> str:
    return resolve_tool_path("FFMPEG_EXE", "ffmpeg", DEFAULT_WINDOWS_FFMPEG)



def get_ffprobe_exe() -> str:
    return resolve_tool_path("FFPROBE_EXE", "ffprobe", DEFAULT_WINDOWS_FFPROBE)
