from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional


def render_video_workspace(*, embedded: bool = False) -> None:
    """Render Video's GUI while keeping Streamlit out of headless imports."""
    from video.gui.app import render_video_workspace as render

    render(embedded=embedded)


def render_video_studio(*args: Any, **kwargs: Any) -> None:
    kwargs.setdefault("embedded", True)
    render_video_workspace(*args, **kwargs)

from video import config
from video.asset_profile_utils import apply_profile_runtime_defaults, resolve_profile_defaults
from video.config import get_ffmpeg_exe, get_ffprobe_exe
from video.encoding_profiles import PROFILE_AUTO, resolve_encoding_profile
from video.error_handling import USER_FACING_EXCEPTIONS
from video.ffmpeg_runner import ensure_tools, get_media_duration_seconds
from video.logging_utils import get_logger
from video.render_slideshow import make_slideshow_video
from video.render_static import make_static_video
from video.run_history import append_run_history, write_run_log
from video.runtime_tools import format_runtime_diagnostics
from video.validation import (
    autodetect_subtitle_from_audio,
    inspect_video_image_readiness,
    resolve_slideshow_cover,
    resolve_slideshow_outro,
    validate_slideshow_inputs,
)
from video.handoff import read_audio_handoff, read_image_handoff
from video.result_manifest import write_result_manifest
from video.media_quality import prepare_audio_for_video, prepare_subtitle_for_video, write_video_quality_report
from video.story_zone_timeline import build_story_zone_segments
from video.slideshow_concat import append_outro_segment, build_slideshow_segments, prepend_cover_segment

logger = get_logger(__name__)


@dataclass
class RenderVideoRequest:
    audio: Optional[Path]
    output: Optional[Path]
    mode: str
    aspect: str
    duration_per_image: float
    subtitle: Optional[Path] = None
    story_json: Optional[Path] = None
    cover: Optional[Path] = None
    scenes_dir: Optional[Path] = None
    cover_first: bool = True
    cover_duration: float = 3.0
    outro_last: bool = True
    outro_duration: float = 5.0
    ffmpeg_exe: Optional[str] = None
    ffprobe_exe: Optional[str] = None
    asset_profile: Optional[str] = None
    profile_root: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    audio_bitrate: Optional[str] = None
    encoding_profile: Optional[str] = PROFILE_AUTO
    loudness_profile: Optional[str] = "narration"
    quality_gate: Optional[bool] = True
    video_preset: Optional[str] = None
    video_crf: Optional[int] = None
    video_fps: Optional[int] = None
    video_tune: Optional[str] = None
    video_movflags: Optional[str] = None
    slideshow_match_audio: Optional[bool] = None
    zone_aware_slideshow: Optional[bool] = None
    audio_match_epsilon: Optional[float] = None
    keep_concat_list: Optional[bool] = None
    subtitle_font_size: Optional[int] = None
    subtitle_outline: Optional[int] = None
    subtitle_shadow: Optional[int] = None
    subtitle_position: Optional[str] = None
    subtitle_alignment: Optional[int] = None
    subtitle_margin_l: Optional[int] = None
    subtitle_margin_r: Optional[int] = None
    subtitle_margin_v: Optional[int] = None
    subtitle_force_style: Optional[str] = None
    ffmpeg_loglevel: Optional[str] = None
    ffmpeg_stream_log: Optional[bool] = None
    ffmpeg_stats: Optional[bool] = None
    show_progress: Optional[bool] = None
    stderr_tail_lines: Optional[int] = None
    print_ffmpeg_version: Optional[bool] = None
    debug_ffmpeg_exe: Optional[bool] = None
    render_video_history_dir: Optional[str] = None
    render_video_history_file: Optional[str] = None
    audio_handoff: Optional[Path] = None
    audio_quality_report: Optional[Path] = None
    image_handoff: Optional[Path] = None


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


def _optional_env_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    raw = str(value).strip()
    return raw or None


@contextlib.contextmanager
def _render_runtime_overrides(request: RenderVideoRequest):
    encoding_profile = resolve_encoding_profile(request.encoding_profile, request.aspect)
    env_overrides = {
        "DEBUG_FFMPEG_EXE": _optional_env_value(request.debug_ffmpeg_exe),
        "SUB_FONT_SIZE": _optional_env_value(request.subtitle_font_size),
        "SUB_OUTLINE": _optional_env_value(request.subtitle_outline),
        "SUB_SHADOW": _optional_env_value(request.subtitle_shadow),
        "SUB_POSITION": _optional_env_value(request.subtitle_position),
        "SUB_ALIGNMENT": _optional_env_value(request.subtitle_alignment),
        "SUB_MARGIN_L": _optional_env_value(request.subtitle_margin_l),
        "SUB_MARGIN_R": _optional_env_value(request.subtitle_margin_r),
        "SUB_MARGIN_V": _optional_env_value(request.subtitle_margin_v),
        "SUB_FORCE_STYLE": _optional_env_value(request.subtitle_force_style),
        "RENDER_VIDEO_HISTORY_DIR": _optional_env_value(request.render_video_history_dir),
        "RENDER_VIDEO_HISTORY_FILE": _optional_env_value(request.render_video_history_file),
    }
    config_overrides = {
        "DEFAULT_ENCODING_PROFILE": encoding_profile.name,
        "DEFAULT_VIDEO_CODEC": request.video_codec or encoding_profile.video_codec,
        "DEFAULT_AUDIO_CODEC": request.audio_codec or encoding_profile.audio_codec,
        "DEFAULT_AUDIO_BITRATE": request.audio_bitrate or encoding_profile.audio_bitrate,
        "DEFAULT_PRESET": request.video_preset or encoding_profile.preset,
        "DEFAULT_CRF": request.video_crf if request.video_crf is not None else encoding_profile.crf,
        "DEFAULT_FPS": request.video_fps if request.video_fps is not None else encoding_profile.fps,
        "DEFAULT_TUNE_STILLIMAGE": request.video_tune or encoding_profile.tune,
        "DEFAULT_PIXEL_FORMAT": encoding_profile.pixel_format,
        "DEFAULT_GOP_SECONDS": encoding_profile.gop_seconds,
        "DEFAULT_MOVFLAGS": request.video_movflags or config.DEFAULT_MOVFLAGS,
        "SLIDESHOW_MATCH_AUDIO": request.slideshow_match_audio,
        "AUDIO_MATCH_EPSILON": request.audio_match_epsilon,
        "KEEP_CONCAT_LIST": request.keep_concat_list,
        "FFMPEG_LOGLEVEL": request.ffmpeg_loglevel,
        "FFMPEG_STREAM_LOG": request.ffmpeg_stream_log,
        "FFMPEG_STATS": request.ffmpeg_stats,
        "SHOW_PROGRESS": request.show_progress,
        "STDERR_TAIL_LINES": request.stderr_tail_lines,
        "PRINT_FFMPEG_VERSION": request.print_ffmpeg_version,
    }
    previous_env = {key: os.environ.get(key) for key in env_overrides}
    previous_config = {key: getattr(config, key) for key in config_overrides if hasattr(config, key)}
    try:
        for key, value in env_overrides.items():
            if value is not None:
                os.environ[key] = value
        for key, value in config_overrides.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
        yield
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key, value in previous_config.items():
            setattr(config, key, value)


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
        raise ValueError("mode must be 'static' or 'slideshow'.")
    if request.aspect not in {"9x16", "16x9"}:
        raise ValueError("aspect must be '9x16' or '16x9'.")
    normalized_profile = str(request.encoding_profile or PROFILE_AUTO).strip().lower()
    if normalized_profile == "tiktok" and request.aspect != "9x16":
        raise ValueError("The tiktok encoding profile requires aspect 9x16.")
    if normalized_profile in {"youtube_4k", "youtube_1080p"} and request.aspect != "16x9":
        raise ValueError(f"The {normalized_profile} encoding profile requires aspect 16x9.")
    if request.duration_per_image <= 0:
        raise ValueError("duration_per_image must be > 0.")
    if request.mode == "slideshow" and request.cover_first and request.cover_duration <= 0:
        raise ValueError("cover_duration must be > 0 when cover_first is enabled.")
    if request.mode == "slideshow" and request.outro_last and request.outro_duration <= 0:
        raise ValueError("outro_duration must be > 0 when outro_last is enabled.")
    if request.audio is None or not str(request.audio).strip():
        raise ValueError("audio path cannot be empty.")
    if request.output is None or not str(request.output).strip():
        raise ValueError("output path cannot be empty.")
    if request.mode == "static" and request.cover is None:
        raise ValueError("Static mode needs a cover image or an asset profile with default_cover.")
    if request.mode == "slideshow" and request.scenes_dir is None:
        raise ValueError("Slideshow mode needs a scenes directory or an asset profile with default_scenes_dir.")
    if request.mode == "slideshow" and request.zone_aware_slideshow:
        if request.story_json is None:
            raise ValueError("Zone-aware slideshow needs a story.json file.")
        if request.subtitle is None:
            raise ValueError("Zone-aware slideshow needs a subtitle .srt file.")
        

def request_from_args(args: Any) -> tuple[RenderVideoRequest, Optional[Path], dict[str, Optional[Path]]]:
    audio_bundle = read_audio_handoff(Path(args.audio_handoff)) if getattr(args, "audio_handoff", None) else None
    image_bundle = read_image_handoff(Path(args.image_handoff)) if getattr(args, "image_handoff", None) else None
    direct_audio = Path(args.audio) if getattr(args, "audio", None) else None
    direct_subtitle = Path(args.subtitle) if getattr(args, "subtitle", None) else None
    direct_cover = Path(args.cover) if getattr(args, "cover", None) else None
    direct_scenes = Path(args.scenes_dir) if getattr(args, "scenes_dir", None) else None
    audio_path = direct_audio or (audio_bundle.audio if audio_bundle else None)
    subtitle_path = direct_subtitle or (audio_bundle.subtitle if audio_bundle else None)
    manifest_cover = image_bundle.cover if image_bundle else None
    manifest_scenes = image_bundle.scenes if image_bundle else None
    profile_dir, defaults, resolved_cover, resolved_scenes_dir = resolve_asset_profile_runtime(
        profile_root=getattr(args, "profile_root", None),
        asset_profile=getattr(args, "asset_profile", None),
        cover=direct_cover or manifest_cover,
        scenes_dir=direct_scenes or manifest_scenes,
    )
    story_json_path = Path(args.story_json) if getattr(args, "story_json", None) else None
    cover_first = bool(getattr(args, "cover_first", True))
    if getattr(args, "mode", None) == "slideshow":
        resolved_cover = resolve_slideshow_cover(
            resolved_cover,
            resolved_scenes_dir,
            cover_first=cover_first,
        )
    if audio_path is None:
        raise ValueError("Provide --audio or --audio-handoff.")
    if subtitle_path is None:
        subtitle_path = autodetect_subtitle_from_audio(audio_path)
    request = RenderVideoRequest(
        audio=audio_path,
        output=Path(args.output),
        mode=args.mode,
        aspect=args.aspect,
        duration_per_image=args.duration_per_image,
        encoding_profile=getattr(args, "encoding_profile", PROFILE_AUTO),
        loudness_profile=getattr(args, "loudness_profile", "narration"),
        quality_gate=bool(getattr(args, "quality_gate", True)),
        subtitle=subtitle_path,
        story_json=story_json_path,
        cover=resolved_cover,
        scenes_dir=resolved_scenes_dir,
        cover_first=cover_first,
        cover_duration=float(getattr(args, "cover_duration", 3.0)),
        outro_last=bool(getattr(args, "outro_last", True)),
        outro_duration=float(getattr(args, "outro_duration", 5.0)),
        asset_profile=getattr(args, "asset_profile", None),
        profile_root=getattr(args, "profile_root", None),
        zone_aware_slideshow=bool(getattr(args, "zone_aware_slideshow", False)),
        audio_handoff=Path(args.audio_handoff) if getattr(args, "audio_handoff", None) else None,
        audio_quality_report=audio_bundle.quality_report if audio_bundle else None,
        image_handoff=Path(args.image_handoff) if getattr(args, "image_handoff", None) else None,
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
    effective_cover = (
        resolve_slideshow_cover(
            request.cover,
            request.scenes_dir,
            cover_first=request.cover_first,
        )
        if request.mode == "slideshow"
        else request.cover
    )
    effective_outro = (
        resolve_slideshow_outro(request.scenes_dir, outro_last=request.outro_last)
        if request.mode == "slideshow"
        else None
    )
    try:
        with _runtime_tool_env(request.ffmpeg_exe, request.ffprobe_exe), _render_runtime_overrides(request):
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                image_readiness = inspect_video_image_readiness(
                    mode=request.mode,
                    aspect=request.aspect,
                    cover=effective_cover,
                    scenes_dir=request.scenes_dir,
                    cover_first=request.cover_first,
                    outro_last=request.outro_last,
                )
                if image_readiness.errors:
                    raise ValueError(
                        "Images are not ready for video render: "
                        + "; ".join(image_readiness.errors)
                    )
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
                with tempfile.TemporaryDirectory(prefix="render_video_audio_") as temp_dir:
                    prepared_audio, audio_preflight = prepare_audio_for_video(
                        request.audio,
                        Path(temp_dir) / "normalized_audio.flac",
                        ffmpeg_exe=request.ffmpeg_exe or get_ffmpeg_exe(),
                        loudness_profile=request.loudness_profile or config.DEFAULT_LOUDNESS_PROFILE,
                    )
                    source_quality_report = request.audio_quality_report
                    if source_quality_report is None:
                        candidate = request.audio.with_name(f"{request.audio.stem}.audio_quality.json")
                        source_quality_report = candidate if candidate.is_file() else None
                    if source_quality_report is not None and source_quality_report.is_file():
                        source_quality = json.loads(source_quality_report.read_text(encoding="utf-8"))
                        audio_preflight["source_quality_report"] = str(source_quality_report.resolve())
                        audio_preflight["source_quality_passed"] = bool(source_quality.get("passed"))
                    render_subtitle, subtitle_auto_wrapped = prepare_subtitle_for_video(
                        request.subtitle,
                        Path(temp_dir) / "wrapped_subtitle.srt",
                    )
                    if request.mode == "static":
                        make_static_video(
                            audio=prepared_audio,
                            cover=effective_cover,
                            aspect=request.aspect,
                            output=request.output,
                            subtitle=render_subtitle,
                            progress_callback=progress_callback,
                        )
                        reference_images = [request.cover] if request.cover is not None else []
                    elif request.mode == "slideshow":
                        make_slideshow_video(
                            audio=prepared_audio,
                            scenes_dir=request.scenes_dir,
                            aspect=request.aspect,
                            output=request.output,
                            cover=request.cover,
                            cover_first=request.cover_first,
                            cover_duration=request.cover_duration,
                            outro_last=request.outro_last,
                            outro_duration=request.outro_duration,
                            duration_per_image=request.duration_per_image,
                            subtitle=render_subtitle,
                            story_json=request.story_json,
                            zone_aware=bool(request.zone_aware_slideshow),
                            progress_callback=progress_callback,
                        )
                        if request.zone_aware_slideshow and request.story_json and request.subtitle and request.scenes_dir:
                            zone_segments = build_story_zone_segments(
                                story_json=request.story_json,
                                subtitle=request.subtitle,
                                scenes_dir=request.scenes_dir,
                            )
                            if request.cover_first and effective_cover is not None and effective_cover.is_file():
                                zone_segments = prepend_cover_segment(
                                    zone_segments,
                                    effective_cover,
                                    request.cover_duration,
                                )
                            zone_segments = append_outro_segment(
                                zone_segments,
                                effective_outro,
                                request.outro_duration,
                            )
                            reference_images = [
                                (segment.image, (segment.start + segment.end) / 2.0)
                                for segment in zone_segments
                            ]
                        else:
                            ordered_images = (
                                validate_slideshow_inputs(prepared_audio, request.scenes_dir)
                                if request.scenes_dir
                                else []
                            )
                            prepared_duration = get_media_duration_seconds(prepared_audio)
                            if effective_cover is not None and effective_cover.is_file():
                                effective_cover_resolved = effective_cover.resolve(strict=False)
                                ordered_images = [
                                    image
                                    for image in ordered_images
                                    if image.resolve(strict=False) != effective_cover_resolved
                                ]
                            if effective_outro is not None and effective_outro.is_file():
                                effective_outro_resolved = effective_outro.resolve(strict=False)
                                ordered_images = [
                                    image
                                    for image in ordered_images
                                    if image.resolve(strict=False) != effective_outro_resolved
                                ]
                            slideshow_segments = build_slideshow_segments(
                                ordered_images,
                                request.duration_per_image,
                                audio_duration=prepared_duration,
                                match_audio=config.SLIDESHOW_MATCH_AUDIO,
                                audio_match_epsilon=config.AUDIO_MATCH_EPSILON,
                            ) if ordered_images else []
                            if request.cover_first and effective_cover is not None and effective_cover.is_file():
                                slideshow_segments = prepend_cover_segment(
                                    slideshow_segments,
                                    effective_cover,
                                    request.cover_duration,
                                )
                            slideshow_segments = append_outro_segment(
                                slideshow_segments,
                                effective_outro,
                                request.outro_duration,
                            )
                            reference_images = [
                                (segment.image, (segment.start + segment.end) / 2.0)
                                for segment in slideshow_segments
                                if segment.start < prepared_duration
                            ]
                    else:
                        raise ValueError("mode must be 'static' or 'slideshow'.")

                output_width, output_height = config.get_output_resolution(request.aspect)
                quality_report, quality = write_video_quality_report(
                    request.output,
                    ffmpeg_exe=request.ffmpeg_exe or get_ffmpeg_exe(),
                    ffprobe_exe=request.ffprobe_exe or get_ffprobe_exe(),
                    loudness_profile=request.loudness_profile or config.DEFAULT_LOUDNESS_PROFILE,
                    expected_width=output_width,
                    expected_height=output_height,
                    expected_fps=config.DEFAULT_FPS,
                    subtitle=request.subtitle,
                    reference_images=reference_images,
                    audio_preflight=audio_preflight,
                    subtitle_auto_wrapped=subtitle_auto_wrapped,
                )
                if bool(request.quality_gate) and not quality["passed"]:
                    failed_checks = ", ".join(name for name, passed in quality["checks"].items() if not passed)
                    raise RuntimeError(f"Video quality gate failed ({failed_checks}). Report: {quality_report}")
                result_manifest = write_result_manifest(
                    request.output.with_suffix(".result.json"),
                    video=request.output,
                    quality_report=quality_report,
                    duration_seconds=quality["duration"]["container_seconds"],
                    resolution=f"{output_width}x{output_height}",
                    input_manifests=(
                        path for path in (request.audio_handoff, request.image_handoff) if path is not None
                    ),
                )
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
                "effective_cover": str(effective_cover) if effective_cover is not None else None,
                "effective_outro": str(effective_outro) if effective_outro is not None else None,
                "status": status,
                "elapsed_seconds": elapsed_seconds,
                "log_file": str(log_path),
            }
        )
        result["history_file"] = str(history_path)
        result["log_file"] = str(log_path)
        result["status"] = status
        result["elapsed_seconds"] = str(elapsed_seconds)
        if status == "ok":
            result["result_manifest_path"] = str(result_manifest)
            result["quality_report_path"] = str(quality_report)
    return result


validate_request = validate_render_request
execute_request = execute_render_request

__all__ = [
    "RenderVideoRequest", "execute_render_request", "execute_request",
    "render_video_studio", "render_video_workspace", "request_from_args",
    "resolve_asset_profile_runtime", "validate_render_request", "validate_request",
    "read_audio_handoff", "read_image_handoff", "write_result_manifest",
]
