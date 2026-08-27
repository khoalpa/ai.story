from __future__ import annotations

import json
import math
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from video import config


@dataclass(frozen=True)
class LoudnessTarget:
    integrated_lufs: float
    true_peak_dbtp: float
    loudness_range_lu: float


LOUDNESS_TARGETS = {
    "narration": LoudnessTarget(-16.0, -1.5, 9.0),
    "social_video": LoudnessTarget(-14.0, -1.0, 9.0),
    "broadcast": LoudnessTarget(-23.0, -2.0, 7.0),
}

_LOUDNORM_JSON_RE = re.compile(r"\{\s*\"input_i\".*?\}", re.DOTALL)
_SSIM_RE = re.compile(r"All:([0-9.]+)")
_BLACK_RE = re.compile(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)")


def _run_quality_command(cmd: list[str], *, step: str) -> subprocess.CompletedProcess[str]:
    timeout = config.QUALITY_CHECK_TIMEOUT_SECONDS
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Video quality check '{step}' timed out after {timeout:g} seconds."
        ) from exc


def normalize_loudness_profile(value: object) -> str:
    normalized = str(value or "narration").strip().lower()
    return normalized if normalized in LOUDNESS_TARGETS else "narration"


def get_loudness_target(profile: object) -> LoudnessTarget:
    return LOUDNESS_TARGETS[normalize_loudness_profile(profile)]


def analyze_loudness(audio: Path, ffmpeg_exe: str, target: LoudnessTarget) -> dict[str, float]:
    audio_filter = (
        f"loudnorm=I={target.integrated_lufs}:LRA={target.loudness_range_lu}:"
        f"TP={target.true_peak_dbtp}:print_format=json"
    )
    proc = _run_quality_command(
        [ffmpeg_exe, "-hide_banner", "-nostats", "-i", str(audio), "-vn", "-af", audio_filter, "-f", "null", os.devnull],
        step="loudness analysis",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Unable to measure loudness: {proc.stderr[-2000:]}")
    matches = _LOUDNORM_JSON_RE.findall(proc.stderr or "")
    if not matches:
        raise RuntimeError("FFmpeg loudnorm did not return measurement JSON")
    raw = json.loads(matches[-1])
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    return {key: float(raw[key]) for key in keys}


def _build_two_pass_filter(target: LoudnessTarget, measured: dict[str, float]) -> str:
    return (
        f"loudnorm=I={target.integrated_lufs}:LRA={target.loudness_range_lu}:TP={target.true_peak_dbtp}:"
        f"measured_I={measured['input_i']}:measured_LRA={measured['input_lra']}:"
        f"measured_TP={measured['input_tp']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )


def audio_meets_target(measured: dict[str, float], target: LoudnessTarget) -> bool:
    return (
        math.isfinite(measured["input_i"])
        and abs(measured["input_i"] - target.integrated_lufs) <= 0.5
        and measured["input_tp"] <= target.true_peak_dbtp + 0.1
    )


def prepare_audio_for_video(
    audio: Path,
    output_flac: Path,
    *,
    ffmpeg_exe: str,
    loudness_profile: str,
) -> tuple[Path, dict]:
    target = get_loudness_target(loudness_profile)
    measured = analyze_loudness(audio, ffmpeg_exe, target)
    if audio_meets_target(measured, target):
        return audio, {"normalized": False, "input": measured}
    output_flac.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(audio),
        "-vn", "-af", _build_two_pass_filter(target, measured),
        "-ar", "48000", "-ac", "2", "-c:a", "flac", str(output_flac),
    ]
    proc = _run_quality_command(cmd, step="audio normalization")
    if proc.returncode != 0:
        raise RuntimeError(f"Unable to normalize video audio: {proc.stderr[-2000:]}")
    return output_flac, {"normalized": True, "input": measured}


def probe_media(path: Path, ffprobe_exe: str) -> dict:
    proc = _run_quality_command(
        [
            ffprobe_exe, "-v", "error", "-show_entries",
            "format=duration,size,bit_rate,start_time:stream=index,codec_name,profile,level,codec_type,width,height,"
            "pix_fmt,r_frame_rate,avg_frame_rate,bit_rate,sample_rate,channels,channel_layout,duration,"
            "start_time,"
            "sample_aspect_ratio,display_aspect_ratio,color_range,color_space,color_transfer,color_primaries",
            "-of", "json", str(path),
        ],
        step="media probe",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Unable to inspect rendered video: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout or "{}")


def _fraction(value: object) -> float:
    raw = str(value or "0/1")
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        return float(numerator) / float(denominator or 1)
    return float(raw or 0)


def _is_faststart(path: Path) -> bool:
    with path.open("rb") as handle:
        header = handle.read(min(path.stat().st_size, 4 * 1024 * 1024))
    moov = header.find(b"moov")
    mdat = header.find(b"mdat")
    return moov >= 0 and (mdat < 0 or moov < mdat)


def _decode_check(path: Path, ffmpeg_exe: str) -> tuple[bool, str, list[dict[str, float]]]:
    proc = _run_quality_command(
        [
            ffmpeg_exe, "-v", "info", "-nostats", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0",
            "-vf", "blackdetect=d=0.5:pix_th=0.10", "-f", "null", os.devnull,
        ],
        step="decode validation",
    )
    stderr = proc.stderr or ""
    black_segments = [
        {"start_seconds": float(start), "end_seconds": float(end), "duration_seconds": float(duration)}
        for start, end, duration in _BLACK_RE.findall(stderr)
    ]
    return proc.returncode == 0, (stderr[-4000:] if proc.returncode != 0 else ""), black_segments


def _parse_srt_timestamp(raw: str) -> float:
    hours, minutes, rest = raw.strip().replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def inspect_subtitle(subtitle: Optional[Path], duration: float) -> dict:
    if subtitle is None or not subtitle.is_file():
        return {"present": False, "timing_ok": True, "line_length_ok": True, "max_end_seconds": None, "long_lines": []}
    text = subtitle.read_text(encoding="utf-8-sig", errors="replace")
    timestamps = re.findall(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})", text)
    max_end = max((_parse_srt_timestamp(value) for value in timestamps), default=0.0)
    content_lines = [line.strip() for line in text.splitlines() if line.strip() and "-->" not in line and not line.strip().isdigit()]
    long_lines = [line for line in content_lines if len(line) > 70]
    return {
        "present": True,
        "timing_ok": max_end <= duration + 0.1,
        "line_length_ok": not long_lines,
        "max_end_seconds": max_end,
        "long_lines": long_lines[:20],
    }


def prepare_subtitle_for_video(
    subtitle: Optional[Path],
    output: Path,
    max_chars: Optional[int] = None,
) -> tuple[Optional[Path], bool]:
    """Prepare SRT while leaving default line wrapping to libass.

    A fixed character count does not represent rendered width and can force
    short-looking three-line subtitles even when the configured left/right
    margins leave ample room. Callers may still request hard wrapping by
    passing ``max_chars`` explicitly.
    """
    if subtitle is None or not subtitle.is_file() or subtitle.suffix.lower() != ".srt":
        return subtitle, False
    text = subtitle.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    rendered_blocks = []
    changed = False
    for block in blocks:
        lines = block.splitlines()
        time_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            rendered_blocks.append(block)
            continue
        prefix = lines[: time_index + 1]
        body: list[str] = []
        for line in lines[time_index + 1 :]:
            normalized_line = line.strip()
            wrapped = (
                textwrap.wrap(
                    normalized_line,
                    width=max_chars,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                if max_chars is not None
                else [normalized_line]
            ) or [""]
            # Preserve long lines for margin-aware libass wrapping while
            # marking them as layout-managed for the quality gate.
            changed = changed or (max_chars is None and len(normalized_line) > 70)
            changed = changed or len(wrapped) > 1
            body.extend(wrapped)
        rendered_blocks.append("\n".join(prefix + body))
    if not changed:
        return subtitle, False
    output.write_text("\n\n".join(rendered_blocks) + "\n", encoding="utf-8")
    return output, True


def sample_visual_ssim(
    video: Path,
    references: Iterable[Path | tuple[Path, float]],
    *,
    width: int,
    height: int,
    duration: float,
    ffmpeg_exe: str,
) -> list[dict]:
    refs = []
    for item in references:
        path, timestamp = item if isinstance(item, tuple) else (item, None)
        if path.is_file():
            refs.append((path, timestamp))
    if not refs:
        return []
    results = []
    for index, (reference, requested_timestamp) in enumerate(refs):
        timestamp = requested_timestamp if requested_timestamp is not None else duration * (index + 0.5) / len(refs)
        filter_complex = (
            f"[0:v]format=yuv420p,setpts=PTS-STARTPTS[video];"
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[reference];"
            "[video][reference]ssim"
        )
        proc = _run_quality_command(
            [
                ffmpeg_exe, "-hide_banner", "-loglevel", "info", "-ss", f"{timestamp:.3f}", "-i", str(video),
                "-loop", "1", "-i", str(reference), "-filter_complex", filter_complex,
                "-frames:v", "1", "-an", "-f", "null", os.devnull,
            ],
            step=f"visual SSIM sample {index + 1}",
        )
        match = _SSIM_RE.search(proc.stderr or "")
        results.append({
            "reference": reference.name,
            "timestamp_seconds": timestamp,
            "ssim": float(match.group(1)) if match else None,
            "return_code": proc.returncode,
            "error": "" if match else (proc.stderr or "")[-2000:],
        })
    return results


def write_video_quality_report(
    video: Path,
    *,
    ffmpeg_exe: str,
    ffprobe_exe: str,
    loudness_profile: str,
    expected_width: int,
    expected_height: int,
    expected_fps: int,
    subtitle: Optional[Path] = None,
    reference_images: Iterable[Path | tuple[Path, float]] = (),
    audio_preflight: Optional[dict] = None,
    subtitle_auto_wrapped: bool = False,
) -> tuple[Path, dict]:
    probe = probe_media(video, ffprobe_exe)
    streams = probe.get("streams") or []
    video_stream: dict[str, Any] = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), {}
    )
    audio_stream: dict[str, Any] = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), {}
    )
    format_duration = float((probe.get("format") or {}).get("duration") or 0.0)
    video_duration = float(video_stream.get("duration") or format_duration)
    audio_duration = float(audio_stream.get("duration") or format_duration)
    duration_delta = abs(video_duration - audio_duration)
    video_start = float(video_stream.get("start_time") or 0.0)
    audio_start = float(audio_stream.get("start_time") or 0.0)
    start_delta = abs(video_start - audio_start)
    target = get_loudness_target(loudness_profile)
    loudness = analyze_loudness(video, ffmpeg_exe, target)
    decode_ok, decode_errors, black_segments = _decode_check(video, ffmpeg_exe)
    subtitle_report = inspect_subtitle(subtitle, format_duration)
    visual_samples = sample_visual_ssim(
        video, reference_images, width=expected_width, height=expected_height,
        duration=format_duration, ffmpeg_exe=ffmpeg_exe,
    )
    valid_ssim = [sample["ssim"] for sample in visual_samples if sample["ssim"] is not None]
    all_visual_samples_measured = len(valid_ssim) == len(visual_samples)
    checks = {
        "integrated_loudness": abs(loudness["input_i"] - target.integrated_lufs) <= 1.0,
        "true_peak": loudness["input_tp"] <= target.true_peak_dbtp + 0.2,
        "av_duration_sync": duration_delta <= 0.1 and start_delta <= 0.1,
        "resolution": int(video_stream.get("width") or 0) == expected_width and int(video_stream.get("height") or 0) == expected_height,
        "square_pixels": str(video_stream.get("sample_aspect_ratio") or "1:1") in {"1:1", "N/A"},
        "frame_rate": abs(_fraction(video_stream.get("avg_frame_rate")) - expected_fps) <= 0.01,
        "video_codec": video_stream.get("codec_name") in {"h264", "hevc", "av1"},
        "pixel_format": video_stream.get("pix_fmt") in {"yuv420p", "yuv420p10le"},
        "bt709_color": (
            video_stream.get("color_primaries") == "bt709"
            and video_stream.get("color_transfer") == "bt709"
            and video_stream.get("color_space") == "bt709"
            and video_stream.get("color_range") == "tv"
        ),
        "audio_codec": audio_stream.get("codec_name") == "aac",
        "audio_sample_rate": int(audio_stream.get("sample_rate") or 0) == 48000,
        "audio_channels": int(audio_stream.get("channels") or 0) == 2,
        "faststart": _is_faststart(video),
        "non_negative_start": float((probe.get("format") or {}).get("start_time") or 0.0) >= -0.01,
        "decode": decode_ok,
        "black_frames": sum(segment["duration_seconds"] for segment in black_segments) <= 1.0,
        "subtitle_timing": subtitle_report["timing_ok"],
        "subtitle_line_length": subtitle_report["line_length_ok"] or subtitle_auto_wrapped,
        "visual_ssim": not visual_samples or (
            all_visual_samples_measured and min(valid_ssim) >= 0.90
        ),
    }
    report = {
        "schema_version": 1,
        "video_file": str(video.resolve()),
        "loudness_profile": normalize_loudness_profile(loudness_profile),
        "audio_preflight": audio_preflight or {},
        "target": {"integrated_lufs": target.integrated_lufs, "true_peak_dbtp": target.true_peak_dbtp},
        "measured": {"integrated_lufs": loudness["input_i"], "true_peak_dbtp": loudness["input_tp"], "loudness_range_lu": loudness["input_lra"]},
        "duration": {
            "container_seconds": format_duration,
            "video_seconds": video_duration,
            "audio_seconds": audio_duration,
            "delta_seconds": duration_delta,
            "video_start_seconds": video_start,
            "audio_start_seconds": audio_start,
            "start_delta_seconds": start_delta,
        },
        "video_stream": video_stream,
        "audio_stream": audio_stream,
        "subtitle": {**subtitle_report, "auto_wrapped": bool(subtitle_auto_wrapped)},
        "visual_samples": visual_samples,
        "black_segments": black_segments,
        "decode_errors": decode_errors,
        "checks": checks,
        "passed": all(checks.values()),
    }
    report_path = video.with_name(f"{video.stem}.video_quality.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path, report
