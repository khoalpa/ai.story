from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

POST_FX_PRESET_NONE = "none"
POST_FX_PRESET_STORYTELLING_VI = "storytelling_vi"
SUPPORTED_AUDIO_FORMATS = {"wav", "mp3"}
DEFAULT_AUDIO_FORMAT = "wav"
LOUDNESS_PROFILE_NARRATION = "narration"
LOUDNESS_PROFILE_SOCIAL_VIDEO = "social_video"
LOUDNESS_PROFILE_BROADCAST = "broadcast"
DEFAULT_LOUDNESS_PROFILE = LOUDNESS_PROFILE_NARRATION
SUPPORTED_LOUDNESS_PROFILES = {
    LOUDNESS_PROFILE_NARRATION,
    LOUDNESS_PROFILE_SOCIAL_VIDEO,
    LOUDNESS_PROFILE_BROADCAST,
}
DEFAULT_MP3_BITRATE_KBPS = 192


@dataclass(frozen=True)
class LoudnessTarget:
    integrated_lufs: float
    true_peak_dbtp: float
    loudness_range_lu: float


LOUDNESS_TARGETS = {
    LOUDNESS_PROFILE_NARRATION: LoudnessTarget(-16.0, -1.5, 9.0),
    LOUDNESS_PROFILE_SOCIAL_VIDEO: LoudnessTarget(-14.0, -1.0, 9.0),
    LOUDNESS_PROFILE_BROADCAST: LoudnessTarget(-23.0, -2.0, 7.0),
}


def normalize_audio_format(value: object) -> str:
    normalized = str(value or DEFAULT_AUDIO_FORMAT).strip().lower()
    return normalized if normalized in SUPPORTED_AUDIO_FORMATS else DEFAULT_AUDIO_FORMAT


def normalize_loudness_profile(value: object) -> str:
    normalized = str(value or DEFAULT_LOUDNESS_PROFILE).strip().lower()
    return normalized if normalized in SUPPORTED_LOUDNESS_PROFILES else DEFAULT_LOUDNESS_PROFILE


def get_loudness_target(profile: str) -> LoudnessTarget:
    return LOUDNESS_TARGETS[normalize_loudness_profile(profile)]


def build_post_fx_filter_chain(preset: str) -> Optional[str]:
    normalized = (preset or POST_FX_PRESET_NONE).strip().lower()
    if normalized in {"", POST_FX_PRESET_NONE}:
        return None
    if normalized != POST_FX_PRESET_STORYTELLING_VI:
        raise ValueError(f"Unsupported post FX preset: {preset}")
    return ",".join([
        "highpass=f=75",
        "equalizer=f=180:t=q:w=1.0:g=1.0",
        "equalizer=f=320:t=q:w=1.0:g=-1.5",
        "equalizer=f=3000:t=q:w=1.2:g=2.0",
        "acompressor=threshold=0.125:ratio=2:attack=10:release=150:makeup=1.5",
        "deesser=i=0.12:m=0.35:f=0.50:s=i",
    ])


def build_final_output_filter_chain(preset: str) -> Optional[str]:
    return build_post_fx_filter_chain(preset)


def get_output_codec_args(audio_format: str, mp3_bitrate_kbps: int = DEFAULT_MP3_BITRATE_KBPS) -> list[str]:
    if normalize_audio_format(audio_format) == "mp3":
        bitrate = min(320, max(96, int(mp3_bitrate_kbps)))
        return ["-acodec", "libmp3lame", "-b:a", f"{bitrate}k", "-write_xing", "1"]
    return ["-acodec", "pcm_s24le"]


_LOUDNORM_JSON_RE = re.compile(r"\{\s*\"input_i\".*?\}", re.DOTALL)


def _loudnorm_base_filter(target: LoudnessTarget, *, print_format: str) -> str:
    return (
        f"loudnorm=I={target.integrated_lufs}:LRA={target.loudness_range_lu}:"
        f"TP={target.true_peak_dbtp}:print_format={print_format}"
    )


def analyze_loudness(
    input_file: Path,
    ffmpeg_exe: str,
    target: LoudnessTarget,
    prefix_filter: Optional[str] = None,
) -> dict[str, float]:
    filters = [prefix_filter] if prefix_filter else []
    filters.append(_loudnorm_base_filter(target, print_format="json"))
    cmd = [
        ffmpeg_exe, "-hide_banner", "-nostats", "-i", str(input_file),
        "-af", ",".join(filters), "-f", "null", os.devnull,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Unable to measure audio loudness: {proc.stderr[-2000:]}")
    matches = _LOUDNORM_JSON_RE.findall(proc.stderr or "")
    if not matches:
        raise RuntimeError("FFmpeg loudnorm did not return measurement JSON")
    raw = json.loads(matches[-1])
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    try:
        return {key: float(raw[key]) for key in keys}
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid FFmpeg loudnorm measurements: {raw!r}") from exc


def build_two_pass_loudnorm_filter(target: LoudnessTarget, measured: dict[str, float]) -> str:
    return (
        f"loudnorm=I={target.integrated_lufs}:LRA={target.loudness_range_lu}:TP={target.true_peak_dbtp}:"
        f"measured_I={measured['input_i']}:measured_LRA={measured['input_lra']}:"
        f"measured_TP={measured['input_tp']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )
