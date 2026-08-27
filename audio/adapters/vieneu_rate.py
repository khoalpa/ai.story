from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from audio.exceptions import TtsError
from audio.pipeline.flow_state import normalize_rate_value
from audio.pipeline.segment_planner import Segment, rate_str_to_factor


def normalize_vieneu_segment_rate(seg: Segment) -> str:
    return normalize_rate_value(getattr(seg, "rate", "") or "", fallback="0%")


def build_atempo_filter(rate: str) -> str:
    factor = max(0.01, rate_str_to_factor(rate))
    factors: list[float] = []
    while factor > 2.0:
        factors.append(2.0)
        factor /= 2.0
    while factor < 0.5:
        factors.append(0.5)
        factor /= 0.5
    if not factors or abs(factor - 1.0) > 1e-9:
        factors.append(factor)
    return ",".join(f"atempo={item:.8g}" for item in factors)


def apply_vieneu_time_stretch(out_wav: Path, *, rate: str, ffmpeg_exe: str = "ffmpeg") -> None:
    normalized_rate = normalize_rate_value(rate, fallback="0%")
    if abs(rate_str_to_factor(normalized_rate) - 1.0) < 1e-9:
        return

    stretched_wav = out_wav.with_name(f".{out_wav.stem}.time_stretch{out_wav.suffix}")
    command = [
        str(ffmpeg_exe or "ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(out_wav),
        "-filter:a",
        build_atempo_filter(normalized_rate),
        "-c:a",
        "pcm_s16le",
        str(stretched_wav),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        os.replace(stretched_wav, out_wav)
    except Exception as exc:
        try:
            stretched_wav.unlink(missing_ok=True)
        except OSError:
            pass
        stderr = str(getattr(exc, "stderr", "") or "").strip()
        detail = f" Details: {stderr}" if stderr else ""
        raise TtsError(f"VieNeu time-stretch failed for rate {normalized_rate}.{detail}") from exc


def apply_vieneu_rate_hint(voice: Any, *, rate: str) -> Any:
    if voice is None:
        return None

    rate_factor = rate_str_to_factor(rate)
    if isinstance(voice, dict):
        updated = dict(voice)
        for key, value in (
            ("rate", rate),
            ("speed", rate_factor),
            ("speaking_rate", rate_factor),
            ("rate_factor", rate_factor),
        ):
            if key in updated:
                updated[key] = value
        return updated

    for attr, value in (
        ("rate", rate),
        ("speed", rate_factor),
        ("speaking_rate", rate_factor),
        ("rate_factor", rate_factor),
    ):
        if hasattr(voice, attr):
            try:
                setattr(voice, attr, value)
            except Exception:
                continue
    return voice
