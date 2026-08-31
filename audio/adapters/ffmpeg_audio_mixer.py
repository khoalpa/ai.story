from __future__ import annotations

import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from audio.adapters.audio_loudness import (
    DEFAULT_AUDIO_FORMAT,
    DEFAULT_LOUDNESS_PROFILE,
    DEFAULT_MP3_BITRATE_KBPS,
    LOUDNESS_PROFILE_BROADCAST,
    LOUDNESS_PROFILE_NARRATION,
    LOUDNESS_PROFILE_SOCIAL_VIDEO,
    POST_FX_PRESET_NONE,
    POST_FX_PRESET_STORYTELLING_VI,
    LoudnessTarget,
    analyze_loudness,
    build_final_output_filter_chain,
    build_two_pass_loudnorm_filter,
    get_loudness_target,
    get_output_codec_args,
    normalize_audio_format,
    normalize_loudness_profile,
)
from audio.adapters.wav_analysis import (
    get_wav_duration_seconds,
    measure_wav_edge_silence,
)
from audio.logging_utils import finish_cli_progress, get_logger, render_cli_progress
from audio.pipeline.segment_planner import Segment

INTERMEDIATE_PCM_CODEC = "pcm_f32le"
DEFAULT_OUTPUT_CHANNELS = 2
SEGMENT_LOUDNESS_MAX_DROP_LU = 3.5

PACING_PRESET_OFF = "off"
PACING_PRESET_COMPACT = "compact"
PACING_PRESET_NATURAL = "natural"
PACING_PRESET_DRAMATIC = "dramatic"
DEFAULT_PACING_PRESET = PACING_PRESET_NATURAL
SUPPORTED_PACING_PRESETS = {
    PACING_PRESET_OFF,
    PACING_PRESET_COMPACT,
    PACING_PRESET_NATURAL,
    PACING_PRESET_DRAMATIC,
}

_PACING_TARGETS_MS = {
    PACING_PRESET_OFF: {"sentence": 0, "voice": 0, "paragraph": 0, "zone": 0},
    PACING_PRESET_COMPACT: {"sentence": 350, "voice": 450, "paragraph": 650, "zone": 900},
    PACING_PRESET_NATURAL: {"sentence": 550, "voice": 650, "paragraph": 800, "zone": 1200},
    PACING_PRESET_DRAMATIC: {"sentence": 750, "voice": 850, "paragraph": 1100, "zone": 1500},
}

logger = get_logger(__name__)

_OUTPUT_RETRY_ATTEMPTS = 4
_OUTPUT_RETRY_DELAY_SECONDS = 0.2


def _cleanup_render_temp_dir(temp_dir: Path) -> None:
    try:
        shutil.rmtree(temp_dir)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Unable to remove render temp directory %s: %s", temp_dir, exc)


def normalize_pacing_preset(value: object) -> str:
    normalized = str(value or DEFAULT_PACING_PRESET).strip().lower()
    return normalized if normalized in SUPPORTED_PACING_PRESETS else DEFAULT_PACING_PRESET


def boundary_pause_target_ms(previous: Segment, current: Segment, pacing_preset: str) -> int:
    """Return the desired total acoustic gap between two spoken segments."""
    targets = _PACING_TARGETS_MS[normalize_pacing_preset(pacing_preset)]
    if (previous.zone or "").strip().lower() != (current.zone or "").strip().lower():
        return targets["zone"]
    if current.paragraph_break_before:
        return targets["paragraph"]
    if previous.voice != current.voice or previous.lang != current.lang:
        return targets["voice"]
    return targets["sentence"]


def get_output_progress_label(audio_format: str, has_filter_chain: bool = False) -> str:
    if has_filter_chain:
        return "[POST]"
    return "[MP3]" if normalize_audio_format(audio_format) == "mp3" else "[WAV]"


def _sleep_before_retry(attempt: int) -> None:
    time.sleep(_OUTPUT_RETRY_DELAY_SECONDS * (attempt + 1))


def _remove_existing_output(output_file: Path) -> bool:
    if not output_file.exists():
        return True
    try:
        output_file.chmod(0o666)
    except Exception:
        pass
    try:
        output_file.unlink()
        return True
    except FileNotFoundError:
        return True
    except PermissionError:
        return False


def _iter_output_fallbacks(output_file: Path, max_attempts: int = 20):
    suffix = output_file.suffix
    stem = output_file.stem
    for index in range(1, max_attempts + 1):
        yield output_file.with_name(f"{stem}_{index}{suffix}")


def apply_post_fx(
    input_wav: Path,
    output_file: Path,
    ffmpeg_exe: str,
    ffprobe_exe: str,
    preset: str,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
    sample_rate: int = 48000,
    loudness_profile: str = DEFAULT_LOUDNESS_PROFILE,
    output_channels: int = DEFAULT_OUTPUT_CHANNELS,
    mp3_bitrate_kbps: int = DEFAULT_MP3_BITRATE_KBPS,
    progress_callback: Optional[Callable[[dict], None]] = None,
    duration_seconds: float | None = None,
) -> Path:
    tone_filter_chain = build_final_output_filter_chain(preset)
    loudness_target = get_loudness_target(loudness_profile)
    measured = analyze_loudness(input_wav, ffmpeg_exe, loudness_target, tone_filter_chain)
    filter_parts = [tone_filter_chain] if tone_filter_chain else []
    filter_parts.append(build_two_pass_loudnorm_filter(loudness_target, measured))
    filter_chain = ",".join(filter_parts)
    codec_args = get_output_codec_args(audio_format, mp3_bitrate_kbps)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_output_name = tempfile.mkstemp(
        prefix=f"{output_file.stem}.",
        suffix=f".ffmpeg{output_file.suffix or '.out'}",
        dir=str(output_file.parent),
    )
    os.close(fd)
    staged_output = Path(staged_output_name)

    cmd = [
        ffmpeg_exe, "-y",
        "-progress", "pipe:1",
        "-nostats",
        "-loglevel", "error",
        "-i", str(input_wav),
    ]
    cmd.extend(["-af", filter_chain])
    cmd.extend(["-ar", str(sample_rate), "-ac", str(max(1, min(2, int(output_channels))))])
    cmd.extend(codec_args)
    cmd.append(str(staged_output))

    total_seconds = duration_seconds or get_audio_duration_seconds(input_wav, ffprobe_exe) or 0.001
    label = get_output_progress_label(audio_format, has_filter_chain=True)
    try:
        run_ffmpeg_with_progress(cmd, total_seconds, label=label, progress_callback=progress_callback)
    except Exception:
        try:
            staged_output.unlink(missing_ok=True)
        except Exception:
            pass
        raise

    for attempt in range(_OUTPUT_RETRY_ATTEMPTS):
        if not _remove_existing_output(output_file):
            if attempt < _OUTPUT_RETRY_ATTEMPTS - 1:
                logger.warning(
                    "Output %s is still locked; retrying cleanup (%d/%d) with staged output %s",
                    output_file,
                    attempt + 1,
                    _OUTPUT_RETRY_ATTEMPTS,
                    staged_output,
                )
                _sleep_before_retry(attempt)
                continue
            break
        try:
            os.replace(staged_output, output_file)
            return output_file
        except PermissionError:
            if attempt < _OUTPUT_RETRY_ATTEMPTS - 1:
                logger.warning(
                    "Unable to replace %s on attempt %d/%d; retrying with staged output %s",
                    output_file,
                    attempt + 1,
                    _OUTPUT_RETRY_ATTEMPTS,
                    staged_output,
                )
                _sleep_before_retry(attempt)
                continue
            break
        except OSError:
            if attempt < _OUTPUT_RETRY_ATTEMPTS - 1:
                logger.warning(
                    "Unexpected error replacing %s on attempt %d/%d; retrying with staged output %s",
                    output_file,
                    attempt + 1,
                    _OUTPUT_RETRY_ATTEMPTS,
                    staged_output,
                )
                _sleep_before_retry(attempt)
                continue
            break

    for fallback_file in _iter_output_fallbacks(output_file):
        if not _remove_existing_output(fallback_file):
            continue
        try:
            os.replace(staged_output, fallback_file)
            logger.warning("Output %s was locked; saved final audio as %s", output_file, fallback_file)
            return fallback_file
        except PermissionError:
            continue
        except OSError:
            continue

    logger.warning("Unable to place output under %s or numbered fallbacks; keeping staged output %s", output_file, staged_output)
    return staged_output


@dataclass
class FfmpegMixConfig:
    ffmpeg_exe: str
    ffprobe_exe: str
    intro_clip_file: str = ""
    intro_clip_gain_db: float = 0.0
    outro_clip_file: str = ""
    outro_clip_gain_db: float = 0.0
    bgm_fade_in_default: float = 0.6
    bgm_fade_out_default: float = 0.6
    post_fx_preset: str = POST_FX_PRESET_NONE
    loudness_profile: str = DEFAULT_LOUDNESS_PROFILE
    output_channels: int = DEFAULT_OUTPUT_CHANNELS
    mp3_bitrate_kbps: int = DEFAULT_MP3_BITRATE_KBPS
    enable_bgm_ducking: bool = True
    quality_gate: bool = True
    pacing_preset: str = DEFAULT_PACING_PRESET


def get_audio_duration_seconds(audio_path: Path, ffprobe_exe: str) -> Optional[float]:
    wav_duration = get_wav_duration_seconds(audio_path) if audio_path.suffix.lower() == ".wav" else None
    if wav_duration is not None:
        return wav_duration

    try:
        cmd = [
            ffprobe_exe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            return None
        out = proc.stdout.strip()
        if not out:
            return None
        duration = float(out)
        return duration if duration > 0 else None
    except Exception:
        return None


def probe_audio_stream(audio_path: Path, ffprobe_exe: str) -> dict:
    cmd = [
        ffprobe_exe, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_fmt,sample_rate,channels,channel_layout,bit_rate",
        "-show_entries", "format=duration,bit_rate", "-of", "json", str(audio_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Unable to inspect final audio: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout or "{}")


def write_audio_quality_report(
    audio_path: Path,
    *,
    source_duration_seconds: float,
    ffmpeg_exe: str,
    ffprobe_exe: str,
    loudness_profile: str,
    expected_sample_rate: int,
    expected_channels: int,
    segment_files: Optional[list[Path]] = None,
    mix_segments: Optional[List[Segment]] = None,
    bgm_ducking_enabled: bool = True,
    pacing_preset: str = DEFAULT_PACING_PRESET,
    boundary_measurements: Optional[list[dict]] = None,
) -> tuple[Path, dict]:
    profile = normalize_loudness_profile(loudness_profile)
    target = get_loudness_target(profile)
    measured = analyze_loudness(audio_path, ffmpeg_exe, target)
    probe = probe_audio_stream(audio_path, ffprobe_exe)
    streams = probe.get("streams") or [{}]
    stream = streams[0] if streams else {}
    format_info = probe.get("format") or {}
    try:
        actual_duration = float(format_info.get("duration") or 0.0)
    except (TypeError, ValueError):
        actual_duration = 0.0
    if actual_duration <= 0.0:
        actual_duration = get_audio_duration_seconds(audio_path, ffprobe_exe) or 0.0
    duration_delta = abs(actual_duration - max(0.0, float(source_duration_seconds)))
    segment_measurements: list[dict] = []
    valid_segment_files = [path for path in (segment_files or []) if path.is_file()]

    def measure_segment(path: Path) -> Optional[dict]:
        try:
            value = analyze_loudness(path, ffmpeg_exe, target)["input_i"]
        except Exception as exc:
            logger.warning("Unable to measure segment loudness for %s: %s", path, exc)
            return None
        if not math.isfinite(value):
            return None
        return {"file": path.name, "integrated_lufs": value}

    if valid_segment_files:
        with ThreadPoolExecutor(max_workers=min(4, len(valid_segment_files))) as executor:
            segment_measurements = [item for item in executor.map(measure_segment, valid_segment_files) if item]

    segment_loudness_values = [item["integrated_lufs"] for item in segment_measurements]
    segment_median = statistics.median(segment_loudness_values) if segment_loudness_values else None
    quiet_segment_limit = (
        segment_median - SEGMENT_LOUDNESS_MAX_DROP_LU
        if segment_median is not None
        else None
    )
    quiet_segments = [
        item for item in segment_measurements
        if quiet_segment_limit is not None and item["integrated_lufs"] < quiet_segment_limit
    ]
    bgm_gains = [
        float(segment.bgm_gain_db) if segment.bgm_gain_db is not None else -18.0
        for segment in (mix_segments or [])
        if str(segment.bgm or "").strip()
    ]
    ambience_gains = [
        float(segment.ambience_gain_db) if segment.ambience_gain_db is not None else -24.0
        for segment in (mix_segments or [])
        if str(segment.ambience or "").strip()
    ]
    voice_background_balance = (
        (not bgm_gains or (bgm_ducking_enabled and max(bgm_gains) <= -12.0))
        and (not ambience_gains or max(ambience_gains) <= -18.0)
    )
    checks = {
        "integrated_loudness": abs(measured["input_i"] - target.integrated_lufs) <= 1.0,
        "true_peak": measured["input_tp"] <= target.true_peak_dbtp + 0.2,
        "duration": duration_delta <= 0.1,
        "sample_rate": int(stream.get("sample_rate") or 0) == int(expected_sample_rate),
        "channels": int(stream.get("channels") or 0) == int(expected_channels),
        "segment_loudness_consistency": not quiet_segments,
        "voice_background_balance": voice_background_balance,
    }
    report = {
        "schema_version": 1,
        "audio_file": str(audio_path.resolve()),
        "profile": profile,
        "target": {
            "integrated_lufs": target.integrated_lufs,
            "true_peak_dbtp": target.true_peak_dbtp,
            "loudness_range_lu": target.loudness_range_lu,
        },
        "measured": {
            "integrated_lufs": measured["input_i"],
            "true_peak_dbtp": measured["input_tp"],
            "loudness_range_lu": measured["input_lra"],
            "threshold_lufs": measured["input_thresh"],
        },
        "duration": {
            "source_seconds": source_duration_seconds,
            "output_seconds": actual_duration,
            "delta_seconds": duration_delta,
        },
        "stream": stream,
        "segments": {
            "measured_count": len(segment_measurements),
            "median_lufs": segment_median,
            "maximum_drop_from_median_lu": SEGMENT_LOUDNESS_MAX_DROP_LU,
            "quiet_segments": quiet_segments,
            "measurements": segment_measurements,
        },
        "mix": {
            "bgm_ducking_enabled": bool(bgm_ducking_enabled),
            "maximum_bgm_gain_db": max(bgm_gains) if bgm_gains else None,
            "maximum_ambience_gain_db": max(ambience_gains) if ambience_gains else None,
            "maximum_allowed_bgm_gain_db": -12.0,
            "maximum_allowed_ambience_gain_db": -18.0,
        },
        "pacing": {
            "preset": normalize_pacing_preset(pacing_preset),
            "boundary_count": len(boundary_measurements or []),
            "boundaries": boundary_measurements or [],
        },
        "checks": checks,
        "passed": all(checks.values()),
    }
    report_path = audio_path.with_name(f"{audio_path.stem}.audio_quality.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path, report


def resolve_audio_clip_path(file_name: Optional[str], bgm_dir: Path, out_dir: Path) -> Optional[Path]:
    if not file_name:
        return None
    raw = str(file_name).strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_file():
        return candidate.resolve()
    if not candidate.is_absolute():
        cand_bgm = bgm_dir / raw
        if cand_bgm.is_file():
            return cand_bgm.resolve()
        cand_out = out_dir / raw
        if cand_out.is_file():
            return cand_out.resolve()
    return None


def _hhmmss_to_seconds(ts: str) -> float:
    ts = ts.strip()
    if not ts:
        return 0.0
    if "." in ts:
        hms, frac = ts.split(".", 1)
        frac_s = float("0." + "".join(ch for ch in frac if ch.isdigit()))
    else:
        hms, frac_s = ts, 0.0
    parts = hms.split(":")
    if len(parts) != 3:
        return 0.0
    h, m, s = parts
    return int(h) * 3600 + int(m) * 60 + int(s) + frac_s


def format_hms(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:d}:{s:02d}"


def run_ffmpeg_with_progress(cmd, total_seconds: float, label: str = "[FFMPEG]", progress_callback: Optional[Callable[[dict], None]] = None):
    total_seconds = max(0.001, float(total_seconds))
    is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    last_pct = -1
    captured_tail = []
    last_len = 0

    def _render_progress_line(msg: str, endline: bool = False) -> None:
        nonlocal last_len
        rendered = render_cli_progress(label, msg) if is_tty else False
        if not rendered:
            if endline:
                logger.info(msg)
            return
        last_len = len(msg)
        if endline:
            finish_cli_progress()
            last_len = 0

    for raw in proc.stdout:
        line = (raw or "").strip()
        if not line:
            continue
        captured_tail.append(line)
        if len(captured_tail) > 50:
            captured_tail.pop(0)
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "out_time":
            out_sec = _hhmmss_to_seconds(v.strip())
            pct = int(min(100.0, (out_sec / total_seconds) * 100.0))
            if pct != last_pct:
                _render_progress_line(f"{label} {pct:3d}% ({format_hms(out_sec)})", endline=False)
                if progress_callback:
                    progress_callback({"label": label, "seconds": out_sec, "total_seconds": total_seconds, "percent": pct})
                last_pct = pct
        elif k.strip() == "progress" and v.strip() == "end":
            break

    rc = proc.wait()
    if rc != 0:
        if is_tty:
            _render_progress_line("", endline=True)
        tail = "\n".join(captured_tail[-20:])
        raise RuntimeError(f"ffmpeg error (rc={rc}). Last output:\n{tail}")
    _render_progress_line(f"{label} 100% ({format_hms(total_seconds)})", endline=True)
    if progress_callback:
        progress_callback({"label": label, "seconds": total_seconds, "total_seconds": total_seconds, "percent": 100})



def ffmpeg_mix_audio(
    segments: List[Segment],
    out_file: Path,
    bgm_dir: Path,
    sample_rate: int = 48000,
    mix_config: Optional[FfmpegMixConfig] = None,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> Tuple[List[dict], Path]:
    if mix_config is None:
        raise ValueError("mix_config is required")

    normalized_audio_format = normalize_audio_format(audio_format)
    output_channels = max(1, min(2, int(mix_config.output_channels)))

    wav_dir = out_file.parent / f"{out_file.stem}_wav"
    if not wav_dir.is_dir():
        raise FileNotFoundError(f"KhÃ´ng tÃ¬m tháº¥y thÆ° má»¥c wav: {wav_dir}")

    temp_dir = out_file.parent / f"{out_file.stem}_mix_tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        concat_list_path = temp_dir / "concat_list.txt"
        concat_entries: List[str] = []
        timeline: List[dict] = []
        boundary_measurements: List[dict] = []
        current_time = 0.0
    
        def run_ff(cmd):
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                sys.stderr.write(proc.stderr.decode("utf-8", errors="ignore"))
                raise RuntimeError(f"ffmpeg error: {cmd[0]}")
    
        def prepare_clip_for_concat(src_path: Path, tag: str, gain_db: float) -> Path:
            prepared = temp_dir / f"{tag}.wav"
            cmd = [mix_config.ffmpeg_exe, "-y", "-i", str(src_path)]
            if abs(float(gain_db)) >= 1e-9:
                cmd.extend(["-filter:a", f"volume={float(gain_db)}dB"])
            cmd.extend(["-ac", str(output_channels), "-ar", str(sample_rate), "-acodec", INTERMEDIATE_PCM_CODEC, str(prepared)])
            run_ff(cmd)
            return prepared
    
        def build_silence_wav(dst_path: Path, dur_s: float) -> None:
            cmd = [
                mix_config.ffmpeg_exe, "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r={sample_rate}:cl={'stereo' if output_channels == 2 else 'mono'}",
                "-t", f"{dur_s:.3f}",
                "-acodec", INTERMEDIATE_PCM_CODEC,
                str(dst_path),
            ]
            run_ff(cmd)
    
        def normalize_voice_wav(src_path: Path, dst_path: Path) -> None:
            cmd = [
                mix_config.ffmpeg_exe, "-y",
                "-i", str(src_path),
                "-ac", str(output_channels), "-ar", str(sample_rate),
                "-acodec", INTERMEDIATE_PCM_CODEC,
                str(dst_path),
            ]
            run_ff(cmd)
    
        def prepare_piece_for_block(seg: Segment, idx: int) -> Tuple[Optional[Path], float, bool]:
            if seg.pause_ms_before > 0 and not seg.text.strip():
                dur_s = seg.pause_ms_before / 1000.0
                piece = temp_dir / f"piece_{idx:03d}_sil.wav"
                build_silence_wav(piece, dur_s)
                return piece, dur_s, False
            seg_raw_wav = wav_dir / f"seg_{idx:03d}.wav"
            if not seg_raw_wav.is_file():
                return None, 0.0, False
            piece = temp_dir / f"piece_{idx:03d}_voice.wav"
            normalize_voice_wav(seg_raw_wav, piece)
            dur = get_audio_duration_seconds(piece, mix_config.ffprobe_exe) or 0.0
            return piece, dur, bool(seg.text.strip())
    
        def bgm_context_key(seg: Segment) -> tuple:
            bgm_name = (seg.bgm or "").strip().lower()
            bgm_gain = float(seg.bgm_gain_db) if seg.bgm_gain_db is not None else -18.0
            ambience_name = (seg.ambience or "").strip().lower()
            ambience_gain = float(seg.ambience_gain_db) if seg.ambience_gain_db is not None else -24.0
            zone = (seg.zone or "").strip().lower()
            return zone, bgm_name, round(bgm_gain, 4), ambience_name, round(ambience_gain, 4)
    
        def resolve_bgm_path(seg: Segment) -> Optional[Path]:
            raw = (seg.bgm or "").strip()
            if not raw:
                return None
            cand = bgm_dir / raw
            return cand if cand.is_file() else None
    
        def resolve_ambience_path(seg: Segment) -> Optional[Path]:
            raw = (seg.ambience or "").strip()
            if not raw:
                return None
            cand = bgm_dir / raw
            return cand if cand.is_file() else None
    
        def finalize_block(
            block_idx: int,
            piece_paths: List[Path],
            block_bgm_path: Optional[Path],
            block_bgm_gain_db: float,
            block_ambience_path: Optional[Path],
            block_ambience_gain_db: float,
        ):
            if not piece_paths:
                return None, 0.0
            block_concat_path = temp_dir / f"block_{block_idx:03d}_concat.txt"
            with open(block_concat_path, "w", encoding="utf-8") as fh:
                for p in piece_paths:
                    fh.write(f"file '{p.resolve().as_posix()}'\n")
            dry_block = temp_dir / f"block_{block_idx:03d}_dry.wav"
            cmd_concat = [
                mix_config.ffmpeg_exe, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(block_concat_path),
                "-ac", str(output_channels), "-ar", str(sample_rate), "-acodec", INTERMEDIATE_PCM_CODEC,
                str(dry_block),
            ]
            run_ff(cmd_concat)
            block_dur = sum(get_audio_duration_seconds(path, mix_config.ffprobe_exe) or 0.0 for path in piece_paths)
            if block_dur <= 0.0:
                return dry_block, block_dur
            has_bgm = bool(block_bgm_path and block_bgm_path.is_file())
            has_ambience = bool(block_ambience_path and block_ambience_path.is_file())
            if not has_bgm and not has_ambience:
                return dry_block, block_dur
            mixed_block = temp_dir / f"block_{block_idx:03d}_mixed.wav"
            fade_in = max(0.0, float(mix_config.bgm_fade_in_default))
            fade_out = max(0.0, min(float(mix_config.bgm_fade_out_default), block_dur))
            fade_out_start = max(0.0, block_dur - fade_out)
            input_args = [mix_config.ffmpeg_exe, "-y", "-i", str(dry_block)]
            filter_parts = []
            duck_bgm = bool(has_bgm and mix_config.enable_bgm_ducking)
            if duck_bgm:
                filter_parts.append("[0:a]asplit=2[voice][voice_sc]")
                mix_inputs = ["[voice]"]
            else:
                mix_inputs = ["[0:a]"]
            input_idx = 1
            if has_bgm:
                input_args.extend(["-stream_loop", "-1", "-i", str(block_bgm_path)])
                bgm_chain = [f"volume={float(block_bgm_gain_db)}dB"]
                if fade_in > 0:
                    bgm_chain.append(f"afade=t=in:st=0:d={fade_in:.3f}")
                if fade_out > 0 and block_dur > 0:
                    bgm_chain.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}")
                if duck_bgm:
                    filter_parts.append(f"[{input_idx}:a]{','.join(bgm_chain)}[bgm_raw]")
                    filter_parts.append(
                        "[bgm_raw][voice_sc]sidechaincompress="
                        "threshold=0.05:ratio=6:attack=20:release=400:makeup=1[bgm]"
                    )
                else:
                    filter_parts.append(f"[{input_idx}:a]{','.join(bgm_chain)}[bgm]")
                mix_inputs.append("[bgm]")
                input_idx += 1
            if has_ambience:
                input_args.extend(["-stream_loop", "-1", "-i", str(block_ambience_path)])
                ambience_chain = [f"volume={float(block_ambience_gain_db)}dB"]
                if fade_in > 0:
                    ambience_chain.append(f"afade=t=in:st=0:d={fade_in:.3f}")
                if fade_out > 0 and block_dur > 0:
                    ambience_chain.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}")
                filter_parts.append(f"[{input_idx}:a]{','.join(ambience_chain)}[amb]")
                mix_inputs.append("[amb]")
            filter_parts.append(
                f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:"
                "duration=first:dropout_transition=0:normalize=0[a]"
            )
            cmd_mix = input_args + [
                "-filter_complex", ";".join(filter_parts),
                "-map", "[a]",
                "-ac", str(output_channels), "-ar", str(sample_rate), "-acodec", INTERMEDIATE_PCM_CODEC,
                str(mixed_block),
            ]
            run_ff(cmd_mix)
            return mixed_block, block_dur
    
        intro_clip_path = resolve_audio_clip_path(mix_config.intro_clip_file, bgm_dir, out_file.parent)
        outro_clip_path = resolve_audio_clip_path(mix_config.outro_clip_file, bgm_dir, out_file.parent)
    
        if intro_clip_path:
            prepared_intro = prepare_clip_for_concat(intro_clip_path, "intro_clip", mix_config.intro_clip_gain_db)
            intro_dur = get_audio_duration_seconds(prepared_intro, mix_config.ffprobe_exe) or 0.0
            concat_entries.append(f"file '{prepared_intro.resolve().as_posix()}'")
            current_time += intro_dur
    
        total = len(segments)
        block_idx = -1
        current_block_key = None
        current_block_piece_paths: List[Path] = []
        current_block_elapsed = 0.0
        current_block_bgm_path: Optional[Path] = None
        current_block_bgm_gain_db = -18.0
        current_block_ambience_path: Optional[Path] = None
        current_block_ambience_gain_db = -24.0
        previous_spoken_segment: Optional[Segment] = None
        previous_trailing_silence = 0.0
        pacing_preset = normalize_pacing_preset(mix_config.pacing_preset)
    
        def flush_current_block() -> float:
            nonlocal current_block_piece_paths, current_block_elapsed, current_block_bgm_path, current_block_bgm_gain_db, current_block_ambience_path, current_block_ambience_gain_db, current_time
            block_file, block_dur = finalize_block(
                block_idx,
                current_block_piece_paths,
                current_block_bgm_path,
                current_block_bgm_gain_db,
                current_block_ambience_path,
                current_block_ambience_gain_db,
            )
            if block_file:
                concat_entries.append(f"file '{block_file.resolve().as_posix()}'")
                current_time += block_dur
            current_block_piece_paths = []
            current_block_elapsed = 0.0
            current_block_bgm_path = None
            current_block_bgm_gain_db = -18.0
            current_block_ambience_path = None
            current_block_ambience_gain_db = -24.0
            return block_dur
    
        try:
            for idx, seg in enumerate(segments):
                pct = int((idx + 1) * 100 / max(1, total))
                line = f"[MIX] {pct:3d}% ({idx + 1:3d}/{total:3d} segments)"
                if not render_cli_progress("MIX", line):
                    logger.info("%s", line)
                if progress_callback:
                    progress_callback({"stage": "segments", "completed": idx + 1, "total": total, "percent": pct})
                piece_path, piece_dur, has_text = prepare_piece_for_block(seg, idx)
                if piece_path is None:
                    continue
                leading_silence = 0.0
                trailing_silence = 0.0
                if has_text and pacing_preset != PACING_PRESET_OFF:
                    leading_silence, trailing_silence = measure_wav_edge_silence(piece_path)
                seg_key = bgm_context_key(seg)
                if current_block_key is None:
                    block_idx += 1
                    current_block_key = seg_key
                    current_block_bgm_path = resolve_bgm_path(seg)
                    current_block_bgm_gain_db = float(seg.bgm_gain_db) if seg.bgm_gain_db is not None else -18.0
                    current_block_ambience_path = resolve_ambience_path(seg)
                    current_block_ambience_gain_db = float(seg.ambience_gain_db) if seg.ambience_gain_db is not None else -24.0
                elif seg_key != current_block_key:
                    flush_current_block()
                    current_block_key = seg_key
                    block_idx += 1
                    current_block_bgm_path = resolve_bgm_path(seg)
                    current_block_bgm_gain_db = float(seg.bgm_gain_db) if seg.bgm_gain_db is not None else -18.0
                    current_block_ambience_path = resolve_ambience_path(seg)
                    current_block_ambience_gain_db = float(seg.ambience_gain_db) if seg.ambience_gain_db is not None else -24.0
                added_pause_seconds = 0.0
                target_pause_ms = 0
                if has_text and previous_spoken_segment is not None:
                    target_pause_ms = boundary_pause_target_ms(previous_spoken_segment, seg, pacing_preset)
                    existing_gap_seconds = previous_trailing_silence + leading_silence
                    added_pause_seconds = max(0.0, (target_pause_ms / 1000.0) - existing_gap_seconds)
                    if added_pause_seconds >= 0.001:
                        adaptive_pause = temp_dir / f"piece_{idx:03d}_adaptive_pause.wav"
                        build_silence_wav(adaptive_pause, added_pause_seconds)
                        current_block_piece_paths.append(adaptive_pause)
                        current_block_elapsed += added_pause_seconds
                    boundary_measurements.append({
                        "before_segment": idx,
                        "target_ms": target_pause_ms,
                        "existing_ms": int(round(existing_gap_seconds * 1000.0)),
                        "added_ms": int(round(added_pause_seconds * 1000.0)),
                        "result_ms": int(round((existing_gap_seconds + added_pause_seconds) * 1000.0)),
                    })
                piece_offset = current_block_elapsed
                if has_text:
                    timeline.append({"idx": idx, "text": seg.text, "start": current_time + piece_offset, "end": current_time + piece_offset + piece_dur})
                current_block_piece_paths.append(piece_path)
                current_block_elapsed += piece_dur
                if has_text:
                    previous_spoken_segment = seg
                    previous_trailing_silence = trailing_silence
                else:
                    # An explicit PAUSE/SILENCE segment suppresses automatic pacing
                    # across that boundary, preserving the author's instruction.
                    previous_spoken_segment = None
                    previous_trailing_silence = 0.0
    
            if current_block_piece_paths:
                flush_current_block()
        finally:
            finish_cli_progress()
    
        if outro_clip_path:
            prepared_outro = prepare_clip_for_concat(outro_clip_path, "outro_clip", mix_config.outro_clip_gain_db)
            outro_dur = get_audio_duration_seconds(prepared_outro, mix_config.ffprobe_exe) or 0.0
            concat_entries.append(f"file '{prepared_outro.resolve().as_posix()}'")
            current_time += outro_dur
    
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for x in concat_entries:
                f.write(x + "\n")
    
        total_seconds = current_time
        pre_fx_wav = temp_dir / "story_pre_fx.wav"
        cmd_concat_final = [
            mix_config.ffmpeg_exe, "-y",
            "-progress", "pipe:1",
            "-nostats",
            "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list_path),
            "-ac", str(output_channels), "-ar", str(sample_rate),
            "-acodec", INTERMEDIATE_PCM_CODEC,
            str(pre_fx_wav),
        ]
        run_ffmpeg_with_progress(
            cmd_concat_final,
            total_seconds,
            label="[WAV]",
            progress_callback=(lambda data: progress_callback({"stage": "assemble", **data}) if progress_callback else None),
        )
    
        final_out_file = apply_post_fx(
            input_wav=pre_fx_wav,
            output_file=out_file,
            ffmpeg_exe=mix_config.ffmpeg_exe,
            ffprobe_exe=mix_config.ffprobe_exe,
            preset=mix_config.post_fx_preset,
            audio_format=normalized_audio_format,
            sample_rate=sample_rate,
            loudness_profile=mix_config.loudness_profile,
            output_channels=output_channels,
            mp3_bitrate_kbps=mix_config.mp3_bitrate_kbps,
            progress_callback=(lambda data: progress_callback({"stage": "post_fx", **data}) if progress_callback else None),
            duration_seconds=total_seconds,
        )

        actual_total_seconds: float | None = None
        if mix_config.quality_gate:
            report_path, report = write_audio_quality_report(
                final_out_file,
                source_duration_seconds=total_seconds,
                ffmpeg_exe=mix_config.ffmpeg_exe,
                ffprobe_exe=mix_config.ffprobe_exe,
                loudness_profile=mix_config.loudness_profile,
                expected_sample_rate=sample_rate,
                expected_channels=output_channels,
                segment_files=[
                    wav_dir / f"seg_{idx:03d}.wav"
                    for idx, segment in enumerate(segments)
                    if segment.text.strip()
                ],
                mix_segments=segments,
                bgm_ducking_enabled=mix_config.enable_bgm_ducking,
                pacing_preset=pacing_preset,
                boundary_measurements=boundary_measurements,
            )
            if not report["passed"]:
                failed_checks = ", ".join(name for name, passed in report["checks"].items() if not passed)
                raise RuntimeError(f"Audio quality gate failed ({failed_checks}). Report: {report_path}")
            logger.info("Audio quality gate passed: %s", report_path)
            actual_total_seconds = float(report["duration"]["output_seconds"])
    
        if actual_total_seconds is None:
            actual_total_seconds = get_audio_duration_seconds(final_out_file, mix_config.ffprobe_exe)
        if actual_total_seconds is not None and abs(actual_total_seconds - total_seconds) >= 1.0:
            logger.info("%s Final duration: %s", get_output_progress_label(normalized_audio_format), format_hms(actual_total_seconds))
    
        return timeline, final_out_file
    finally:
        _cleanup_render_temp_dir(temp_dir)
