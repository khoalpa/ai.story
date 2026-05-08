from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Optional

from video import config
from video.exceptions import FfmpegExecutionError
from video.logging_utils import get_logger
from video.runtime_tools import ensure_tools as ensure_runtime_tools
from video.runtime_tools import is_available_tool

logger = get_logger(__name__)


def ensure_tools() -> None:
    ensure_runtime_tools(
        config.get_ffmpeg_exe(),
        config.get_ffprobe_exe(),
        print_ffmpeg_version=config.PRINT_FFMPEG_VERSION,
    )


def ensure_output_dir(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)


def ffmpeg_base_args() -> list[str]:
    args = [config.get_ffmpeg_exe(), "-hide_banner", "-loglevel", config.FFMPEG_LOGLEVEL]
    args.append("-stats" if config.FFMPEG_STATS else "-nostats")
    return args


def get_media_duration_seconds(path: Path) -> Optional[float]:
    ffprobe_exe = config.get_ffprobe_exe()
    if not is_available_tool(ffprobe_exe):
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe_exe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        out = proc.stdout.strip()
        return float(out) if out else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def format_hms(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:d}:{s:02d}"


def run_ffmpeg(
    cmd: list[str],
    expected_duration_s: Optional[float] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> None:
    if os.getenv("DEBUG_FFMPEG_EXE", "0").strip() == "1":
        logger.debug("ffmpeg exe: %s", cmd[0])

    if config.FFMPEG_STREAM_LOG or not config.SHOW_PROGRESS:
        if progress_callback is not None:
            progress_callback(0.0, "Bắt đầu render...")
        proc = subprocess.Popen(cmd, stdout=None, stderr=None)
        rc = proc.wait()
        if rc != 0:
            raise FfmpegExecutionError(f"ffmpeg failed, return code={rc}")
        if progress_callback is not None:
            progress_callback(100.0, "Hoàn tất 100%")
        return

    cmd2 = cmd.copy()
    cmd2.insert(1, "-progress")
    cmd2.insert(2, "pipe:1")

    proc = subprocess.Popen(
        cmd2,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    stderr_tail: Deque[str] = deque(maxlen=config.STDERR_TAIL_LINES)

    def _drain_stderr() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            stderr_tail.append(line.rstrip("\n"))

    t = threading.Thread(target=_drain_stderr, daemon=True)
    t.start()

    last_print = 0.0
    started_at = time.time()
    line_ended = True
    out_time_re = re.compile(r"^out_time_ms=(\d+)$")
    out_time_us_re = re.compile(r"^out_time_us=(\d+)$")
    out_time_re2 = re.compile(r"^out_time=(\d+:\d+:\d+\.\d+)$")
    progress_re = re.compile(r"^progress=(\w+)$")
    current_out_s = 0.0

    if proc.stdout is None:
        raise FfmpegExecutionError("Không đọc được stdout progress từ ffmpeg.")

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        m = out_time_re.match(line)
        if m:
            current_out_s = int(m.group(1)) / 1_000_000.0
            continue
        m = out_time_us_re.match(line)
        if m:
            current_out_s = int(m.group(1)) / 1_000_000.0
            continue
        m = out_time_re2.match(line)
        if m:
            parts = m.group(1).split(":")
            if len(parts) == 3:
                h, mm, ss = int(parts[0]), int(parts[1]), float(parts[2])
                current_out_s = h * 3600 + mm * 60 + ss
            continue
        m = progress_re.match(line)
        if not m:
            continue
        status = m.group(1)
        now = time.time()
        if expected_duration_s and expected_duration_s > 0:
            pct = min(100.0, (current_out_s / expected_duration_s) * 100.0)
            if now - last_print >= 0.5 or status != "continue":
                last_print = now
                elapsed = max(0.0, now - started_at)
                eta = None
                if pct > 0.1:
                    eta = max(0.0, elapsed * (100.0 - pct) / pct)
                eta_text = f" eta {format_hms(eta)}" if eta is not None else ""
                msg = f"[MP4] {int(round(pct)):3d}% ({format_hms(current_out_s)}/{format_hms(expected_duration_s)}{eta_text})"
                print(
                    f"\r{msg}",
                    file=sys.stderr,
                    end="" if status == "continue" else "\n",
                    flush=True,
                )
                if progress_callback is not None:
                    progress_callback(pct, msg)
                line_ended = status != "continue"
        else:
            if now - last_print >= 0.5 or status != "continue":
                last_print = now
                msg = f"[TIME] {format_hms(current_out_s)}"
                print(msg, file=sys.stderr, end="\r" if status == "continue" else "\n")
                if progress_callback is not None:
                    progress_callback(0.0, msg)

    rc = proc.wait()
    t.join(timeout=1.0)
    if rc != 0:
        raise FfmpegExecutionError(
            f"ffmpeg failed, return code={rc}\n--- ffmpeg stderr tail ---\n"
            + "\n".join(stderr_tail)
        )
    if progress_callback is not None:
        progress_callback(100.0, "Hoàn tất 100%")
    if not line_ended:
        print("", file=sys.stderr)
