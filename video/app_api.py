from __future__ import annotations

import contextlib
import io
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from video.asset_profile_utils import apply_profile_runtime_defaults, resolve_profile_defaults
from video.config import get_ffmpeg_exe, get_ffprobe_exe
from video.error_handling import USER_FACING_EXCEPTIONS
from video.ffmpeg_runner import ensure_tools
from video.logging_utils import get_logger
from video.render_slideshow import make_slideshow_video
from video.render_static import make_static_video
from video.run_history import append_run_history, write_run_log
from video.runtime_tools import format_runtime_diagnostics
from video.validation import autodetect_subtitle_from_audio

logger = get_logger(__name__)


@dataclass
class RenderVideoRequest:
    audio: Optional[Path]
    output: Optional[Path]
    mode: str
    aspect: str
    duration_per_image: float
    subtitle: Optional[Path] = None
    cover: Optional[Path] = None
    scenes_dir: Optional[Path] = None
    ffmpeg_exe: Optional[str] = None
    ffprobe_exe: Optional[str] = None
    asset_profile: Optional[str] = None
    profile_root: Optional[str] = None


@contextlib.contextmanager
def _runtime_tool_env(ffmpeg_exe: Optional[str], ffprobe_exe: Optional[str]):
    previous = {
        "FFMPEG_EXE": os.environ.get("FFMPEG_EXE"),
        "FFPROBE_EXE": os.environ.get("FFPROBE_EXE"),
    }
    try:
        if ffmpeg_exe:
            os.environ["FFMPEG_EXE"] = ffmpeg_exe
        if ffprobe_exe:
            os.environ["FFPROBE_EXE"] = ffprobe_exe
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def resolve_asset_profile_runtime(
    *,
    profile_root: Optional[str],
    asset_profile: Optional[str],
    cover: Optional[Path],
    scenes_dir: Optional[Path],
) -> tuple[Optional[Path], dict[str, Optional[Path]], Optional[Path], Optional[Path]]:
    defaults = resolve_profile_defaults(profile_root, asset_profile)
    _, resolved_cover, resolved_scenes_dir = apply_profile_runtime_defaults(
        profile_root=profile_root,
        asset_profile=asset_profile,
        cover=cover,
        scenes_dir=scenes_dir,
    )
    profile_dir = defaults.get("profile_dir")
    return profile_dir, defaults, resolved_cover, resolved_scenes_dir


def validate_render_request(request: RenderVideoRequest) -> None:
    if request.mode not in {"static", "slideshow"}:
        raise ValueError("mode phải là 'static' hoặc 'slideshow'.")
    if request.aspect not in {"9x16", "16x9"}:
        raise ValueError("aspect phải là '9x16' hoặc '16x9'.")
    if request.duration_per_image <= 0:
        raise ValueError("duration_per_image phải > 0.")
    if request.audio is None or not str(request.audio).strip():
        raise ValueError("audio path không được để trống.")
    if request.output is None or not str(request.output).strip():
        raise ValueError("output path không được để trống.")
    if request.mode == "static" and request.cover is None:
        raise ValueError("Mode static cần cover image hoặc asset profile có default_cover.")
    if request.mode == "slideshow" and request.scenes_dir is None:
        raise ValueError("Mode slideshow cần scenes directory hoặc asset profile có default_scenes_dir.")
        

def request_from_args(args: Any) -> tuple[RenderVideoRequest, Optional[Path], dict[str, Optional[Path]]]:
    profile_dir, defaults, resolved_cover, resolved_scenes_dir = resolve_asset_profile_runtime(
        profile_root=getattr(args, "profile_root", None),
        asset_profile=getattr(args, "asset_profile", None),
        cover=Path(args.cover) if getattr(args, "cover", None) is not None else None,
        scenes_dir=Path(args.scenes_dir) if getattr(args, "scenes_dir", None) is not None else None,
    )
    subtitle_path = Path(args.subtitle) if getattr(args, "subtitle", None) else None
    audio_path = Path(args.audio)
    if subtitle_path is None:
        subtitle_path = autodetect_subtitle_from_audio(audio_path)
    request = RenderVideoRequest(
        audio=audio_path,
        output=Path(args.output),
        mode=args.mode,
        aspect=args.aspect,
        duration_per_image=args.duration_per_image,
        subtitle=subtitle_path,
        cover=resolved_cover,
        scenes_dir=resolved_scenes_dir,
        asset_profile=getattr(args, "asset_profile", None),
        profile_root=getattr(args, "profile_root", None),
    )
    validate_render_request(request)
    return request, profile_dir, defaults



def execute_render_request(
    request: RenderVideoRequest,
    progress_callback=None,
) -> dict[str, str]:
    started_at = time.perf_counter()
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    status = "ok"
    validate_render_request(request)
    try:
        with _runtime_tool_env(request.ffmpeg_exe, request.ffprobe_exe):
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                logger.info(
                    "Render request mode=%s aspect=%s output=%s",
                    request.mode,
                    request.aspect,
                    request.output,
                )
                logger.info(
                    "Runtime diagnostics\n%s",
                    format_runtime_diagnostics(
                        request.ffmpeg_exe or get_ffmpeg_exe(),
                        request.ffprobe_exe or get_ffprobe_exe(),
                    ),
                )
                ensure_tools()
                if request.mode == "static":
                    make_static_video(
                        audio=request.audio,
                        cover=request.cover,
                        aspect=request.aspect,
                        output=request.output,
                        subtitle=request.subtitle,
                        progress_callback=progress_callback,
                    )
                elif request.mode == "slideshow":
                    make_slideshow_video(
                        audio=request.audio,
                        scenes_dir=request.scenes_dir,
                        aspect=request.aspect,
                        output=request.output,
                        duration_per_image=request.duration_per_image,
                        subtitle=request.subtitle,
                        progress_callback=progress_callback,
                    )
                else:
                    raise ValueError("mode phải là 'static' hoặc 'slideshow'.")
    except USER_FACING_EXCEPTIONS + (RuntimeError, TypeError, AssertionError):
        status = "error"
        raise
    finally:
        result = {"stdout": stdout_buffer.getvalue(), "stderr": stderr_buffer.getvalue()}
        elapsed_seconds = round(time.perf_counter() - started_at, 3)
        log_path = write_run_log(
            stdout=result["stdout"], stderr=result["stderr"], output_hint=str(request.output)
        )
        history_path = append_run_history(
            {
                **asdict(request),
                "status": status,
                "elapsed_seconds": elapsed_seconds,
                "log_file": str(log_path),
            }
        )
        result["history_file"] = str(history_path)
        result["log_file"] = str(log_path)
        result["status"] = status
        result["elapsed_seconds"] = str(elapsed_seconds)
    return result
