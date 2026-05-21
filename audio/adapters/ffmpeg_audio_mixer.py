from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from audio.pipeline.segment_planner import Segment
from audio.logging_utils import finish_cli_progress, get_logger, render_cli_progress
from audio.runtime_checks import validate_runtime_executables


POST_FX_PRESET_NONE = "none"
POST_FX_PRESET_STORYTELLING_VI = "storytelling_vi"
SUPPORTED_AUDIO_FORMATS = {"wav", "mp3"}
DEFAULT_AUDIO_FORMAT = "wav"
FINAL_OUTPUT_GAIN_DB = 3.0
FINAL_OUTPUT_LIMITER = "alimiter=limit=0.97"

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


def normalize_audio_format(value: object) -> str:
    normalized = str(value or DEFAULT_AUDIO_FORMAT).strip().lower()
    return normalized if normalized in SUPPORTED_AUDIO_FORMATS else DEFAULT_AUDIO_FORMAT


def build_post_fx_filter_chain(preset: str) -> Optional[str]:
    """Return an ffmpeg audio filter chain for a named post-FX preset.

    Presets are intentionally conservative because the source material is already
    synthetic/narrated speech. The storytelling_vi chain follows the requested
    order: noise reduction -> EQ -> compressor -> de-esser -> light reverb ->
    peak trim. Some DAW-style parameters do not map 1:1 to ffmpeg filters, so
    we use stable ffmpeg-native approximations instead.
    """
    normalized = (preset or POST_FX_PRESET_NONE).strip().lower()
    if normalized in {"", POST_FX_PRESET_NONE}:
        return None
    if normalized != POST_FX_PRESET_STORYTELLING_VI:
        raise ValueError(f"Unsupported post FX preset: {preset}")

    return ",".join([
        "afftdn=nr=8:nf=-32:tn=1",
        "equalizer=f=80:t=q:w=1.0:g=-6",
        "equalizer=f=150:t=q:w=1.0:g=2",
        "equalizer=f=300:t=q:w=1.0:g=-3",
        "equalizer=f=3000:t=q:w=1.2:g=4",
        "equalizer=f=9000:t=q:w=1.0:g=2",
        "acompressor=threshold=0.1:ratio=3:attack=1:release=100:makeup=1",
        "deesser=i=0.20:m=0.50:f=0.50:s=o",
        "aecho=1.0:0.10:35|55:0.05|0.03",
        "volume=-1dB",
    ])


def build_final_output_filter_chain(preset: str) -> Optional[str]:
    """Return the final ffmpeg filter chain applied to exported audio."""
    filter_parts = []
    preset_chain = build_post_fx_filter_chain(preset)
    if preset_chain:
        filter_parts.append(preset_chain)
    if abs(float(FINAL_OUTPUT_GAIN_DB)) >= 1e-9:
        filter_parts.append(f"volume={float(FINAL_OUTPUT_GAIN_DB)}dB")
        filter_parts.append(FINAL_OUTPUT_LIMITER)
    return ",".join(filter_parts) if filter_parts else None


def get_output_codec_args(audio_format: str) -> list[str]:
    fmt = normalize_audio_format(audio_format)
    if fmt == "mp3":
        return ["-acodec", "libmp3lame", "-qscale:a", "2"]
    return ["-acodec", "pcm_s24le"]


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
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> Path:
    filter_chain = build_final_output_filter_chain(preset)
    codec_args = get_output_codec_args(audio_format)
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
    if filter_chain:
        cmd.extend(["-af", filter_chain])
    cmd.extend(["-ar", str(sample_rate)])
    cmd.extend(codec_args)
    cmd.append(str(staged_output))

    total_seconds = get_audio_duration_seconds(input_wav, ffprobe_exe) or 0.001
    label = get_output_progress_label(audio_format, has_filter_chain=bool(filter_chain))
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


def get_audio_duration_seconds(audio_path: Path, ffprobe_exe: str) -> Optional[float]:
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
        return float(out) if out else None
    except Exception:
        return None


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



def validate_ffmpeg_tools(ffmpeg_exe: str, ffprobe_exe: str):
    """Backward-compatible wrapper retained for older tests/callers."""
    return validate_runtime_executables(ffmpeg_exe, ffprobe_exe)

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
            cmd.extend(["-ac", "1", "-ar", str(sample_rate), "-acodec", "pcm_s16le", str(prepared)])
            run_ff(cmd)
            return prepared
    
        def build_silence_wav(dst_path: Path, dur_s: float) -> None:
            cmd = [
                mix_config.ffmpeg_exe, "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r={sample_rate}:cl=mono",
                "-t", f"{dur_s:.3f}",
                "-acodec", "pcm_s16le",
                str(dst_path),
            ]
            run_ff(cmd)
    
        def normalize_voice_wav(src_path: Path, dst_path: Path) -> None:
            cmd = [
                mix_config.ffmpeg_exe, "-y",
                "-i", str(src_path),
                "-ac", "1", "-ar", str(sample_rate),
                "-acodec", "pcm_s16le",
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
                "-ac", "1", "-ar", str(sample_rate), "-acodec", "pcm_s16le",
                str(dry_block),
            ]
            run_ff(cmd_concat)
            block_dur = get_audio_duration_seconds(dry_block, mix_config.ffprobe_exe) or 0.0
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
            mix_inputs = ["[0:a]"]
            input_idx = 1
            if has_bgm:
                input_args.extend(["-stream_loop", "-1", "-i", str(block_bgm_path)])
                bgm_chain = [f"volume={float(block_bgm_gain_db)}dB"]
                if fade_in > 0:
                    bgm_chain.append(f"afade=t=in:st=0:d={fade_in:.3f}")
                if fade_out > 0 and block_dur > 0:
                    bgm_chain.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}")
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
            filter_parts.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[a]")
            cmd_mix = input_args + [
                "-filter_complex", ";".join(filter_parts),
                "-map", "[a]",
                "-ac", "1", "-ar", str(sample_rate), "-acodec", "pcm_s16le",
                str(mixed_block),
            ]
            run_ff(cmd_mix)
            mixed_dur = get_audio_duration_seconds(mixed_block, mix_config.ffprobe_exe) or block_dur
            return mixed_block, mixed_dur
    
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
                piece_offset = current_block_elapsed
                if has_text:
                    timeline.append({"idx": idx, "text": seg.text, "start": current_time + piece_offset, "end": current_time + piece_offset + piece_dur})
                current_block_piece_paths.append(piece_path)
                current_block_elapsed += piece_dur
    
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
            "-ac", "1", "-ar", str(sample_rate),
            "-acodec", "pcm_s16le",
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
            progress_callback=(lambda data: progress_callback({"stage": "post_fx", **data}) if progress_callback else None),
        )
    
        actual_total_seconds = get_audio_duration_seconds(final_out_file, mix_config.ffprobe_exe)
        if actual_total_seconds is not None and abs(actual_total_seconds - total_seconds) >= 1.0:
            logger.info("%s Final duration: %s", get_output_progress_label(normalized_audio_format), format_hms(actual_total_seconds))
    
        return timeline, final_out_file
    finally:
        _cleanup_render_temp_dir(temp_dir)
