from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from video import config
from video.clip_probe import ClipMetadata, clips_are_copy_compatible, probe_clip
from video.command_builders import (
    build_clip_concat_cmd,
    build_clip_normalize_cmd,
)
from video.encoding_profiles import PROFILE_AUTO, resolve_encoding_profile
from video.ffmpeg_runner import ensure_output_dir, run_ffmpeg
from video.result_manifest import write_result_manifest
from video.slideshow_concat import escape_ffconcat_path

SUPPORTED_CLIP_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass
class ConcatClipsRequest:
    output: Path
    clips: tuple[Path, ...] = ()
    clips_dir: Path | None = None
    pattern: str = "clip_*"
    strategy: str = "auto"
    audio_mode: str = "keep"
    aspect: str = "16x9"
    encoding_profile: str = PROFILE_AUTO
    ffmpeg_exe: str | None = None
    ffprobe_exe: str | None = None
    keep_concat_list: bool = False


@dataclass(frozen=True)
class ConcatClipsResult:
    output: Path
    clips: tuple[Path, ...]
    metadata: tuple[ClipMetadata, ...]
    strategy_used: str
    duration_seconds: float
    result_manifest_path: Path


def natural_sort_key(path: Path) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", path.name)
    )


def discover_clips(clips_dir: Path, pattern: str = "clip_*") -> list[Path]:
    if not clips_dir.is_dir():
        raise ValueError(f"Clips directory not found: {clips_dir}")
    clips = [
        path
        for path in clips_dir.glob(pattern)
        if path.is_file() and path.suffix.casefold() in SUPPORTED_CLIP_EXTENSIONS
    ]
    return sorted(clips, key=natural_sort_key)


def resolve_clip_inputs(request: ConcatClipsRequest) -> list[Path]:
    explicit = list(request.clips)
    discovered = discover_clips(request.clips_dir, request.pattern) if request.clips_dir else []
    clips = explicit or discovered
    if not clips:
        raise ValueError("Provide at least one clip with --clip or --clips-dir.")
    missing = [path for path in clips if not path.is_file()]
    if missing:
        raise ValueError(f"Clip file not found: {missing[0]}")
    output_resolved = request.output.resolve(strict=False)
    if any(path.resolve(strict=False) == output_resolved for path in clips):
        raise ValueError("Output path must not also be an input clip.")
    return clips


def validate_concat_request(request: ConcatClipsRequest) -> None:
    if request.strategy not in {"auto", "copy", "normalize"}:
        raise ValueError("strategy must be auto, copy, or normalize.")
    if request.audio_mode not in {"keep", "mute"}:
        raise ValueError("audio_mode must be keep or mute.")
    if request.aspect not in {"9x16", "16x9"}:
        raise ValueError("aspect must be 9x16 or 16x9.")
    if not str(request.output).strip():
        raise ValueError("output path cannot be empty.")
    resolve_clip_inputs(request)


def write_clip_concat_list(clips: Iterable[Path], output: Path) -> None:
    lines = ["ffconcat version 1.0"]
    lines.extend(f"file '{escape_ffconcat_path(path)}'" for path in clips)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def execute_concat_request(
    request: ConcatClipsRequest,
    progress_callback: Callable[[float, str], None] | None = None,
) -> ConcatClipsResult:
    validate_concat_request(request)
    clips = resolve_clip_inputs(request)
    ffmpeg_exe = request.ffmpeg_exe or config.get_ffmpeg_exe()
    ffprobe_exe = request.ffprobe_exe or config.get_ffprobe_exe()
    metadata = [probe_clip(path, ffprobe_exe=ffprobe_exe) for path in clips]
    include_audio = request.audio_mode == "keep"
    compatible = clips_are_copy_compatible(metadata, include_audio=include_audio)
    if request.strategy == "copy" and not compatible:
        raise ValueError(
            "Clips are not stream-copy compatible; use --strategy auto or normalize."
        )
    strategy = "copy" if request.strategy == "copy" or (
        request.strategy == "auto" and compatible
    ) else "normalize"
    ensure_output_dir(request.output)
    total_duration = sum(item.duration for item in metadata)

    with tempfile.TemporaryDirectory(prefix="concat_clips_") as temp_value:
        temp_dir = Path(temp_value)
        concat_inputs = clips
        if strategy == "normalize":
            profile = resolve_encoding_profile(request.encoding_profile, request.aspect)
            concat_inputs = []
            for index, (clip, info) in enumerate(zip(clips, metadata), start=1):
                normalized = temp_dir / f"clip_{index:04d}.mp4"
                cmd = build_clip_normalize_cmd(
                    ffmpeg_exe=ffmpeg_exe,
                    clip=clip,
                    output=normalized,
                    duration=info.duration,
                    has_audio=info.has_audio,
                    audio_mode=request.audio_mode,
                    width=profile.width,
                    height=profile.height,
                    fps=profile.fps,
                    video_codec=profile.video_codec,
                    preset=profile.preset,
                    crf=profile.crf,
                    pixel_format=profile.pixel_format,
                    audio_codec=profile.audio_codec,
                    audio_bitrate=profile.audio_bitrate,
                )
                if progress_callback:
                    progress_callback(
                        ((index - 1) / max(1, len(clips) + 1)) * 100,
                        f"Normalizing clip {index}/{len(clips)}...",
                    )
                run_ffmpeg(cmd, expected_duration_s=info.duration)
                concat_inputs.append(normalized)

        concat_list = temp_dir / "clips.ffconcat"
        write_clip_concat_list(concat_inputs, concat_list)
        if request.keep_concat_list:
            kept = request.output.with_suffix(".ffconcat")
            write_clip_concat_list(clips, kept)
        cmd = build_clip_concat_cmd(
            ffmpeg_exe=ffmpeg_exe,
            concat_list=concat_list,
            output=request.output,
            audio_mode=request.audio_mode,
        )
        run_ffmpeg(cmd, expected_duration_s=total_duration, progress_callback=progress_callback)

    output_metadata = probe_clip(request.output, ffprobe_exe=ffprobe_exe)
    duration_tolerance = max(1.0, total_duration * 0.05)
    if abs(output_metadata.duration - total_duration) > duration_tolerance:
        raise RuntimeError(
            "Joined video duration differs from the input total: "
            f"expected {total_duration:.3f}s, got {output_metadata.duration:.3f}s."
        )
    result_manifest_path = write_result_manifest(
        request.output.with_suffix(".result.json"),
        video=request.output,
        duration_seconds=output_metadata.duration,
        resolution=f"{output_metadata.width}x{output_metadata.height}",
    )
    return ConcatClipsResult(
        output=request.output,
        clips=tuple(clips),
        metadata=tuple(metadata),
        strategy_used=strategy,
        duration_seconds=output_metadata.duration,
        result_manifest_path=result_manifest_path,
    )
