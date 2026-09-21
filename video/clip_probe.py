from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class ClipMetadata:
    path: Path
    duration: float
    video_codec: str
    width: int
    height: int
    pixel_format: str
    frame_rate: float
    time_base: str
    has_audio: bool
    audio_codec: str | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None

    def video_signature(self) -> tuple[object, ...]:
        return (
            self.video_codec,
            self.width,
            self.height,
            self.pixel_format,
            round(self.frame_rate, 6),
            self.time_base,
        )

    def audio_signature(self) -> tuple[object, ...]:
        return (
            self.has_audio,
            self.audio_codec,
            self.audio_sample_rate,
            self.audio_channels,
        )


def _rate(value: object) -> float:
    raw = str(value or "0/1")
    try:
        return float(Fraction(raw))
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe_clip(path: Path, *, ffprobe_exe: str = "ffprobe") -> ClipMetadata:
    """Read the stream fields that determine safe concat compatibility."""
    try:
        completed = subprocess.run(
            [
                ffprobe_exe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not inspect clip {path}: {exc}") from exc

    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if video is None:
        raise ValueError(f"Clip has no video stream: {path}")
    try:
        duration = float((payload.get("format") or {}).get("duration") or video.get("duration"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Could not determine clip duration: {path}") from exc
    if duration <= 0:
        raise ValueError(f"Clip duration must be positive: {path}")

    return ClipMetadata(
        path=path,
        duration=duration,
        video_codec=str(video.get("codec_name") or ""),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        pixel_format=str(video.get("pix_fmt") or ""),
        frame_rate=_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        time_base=str(video.get("time_base") or ""),
        has_audio=audio is not None,
        audio_codec=str(audio.get("codec_name") or "") if audio else None,
        audio_sample_rate=int(audio.get("sample_rate") or 0) if audio else None,
        audio_channels=int(audio.get("channels") or 0) if audio else None,
    )


def clips_are_copy_compatible(
    clips: list[ClipMetadata], *, include_audio: bool = True
) -> bool:
    if not clips:
        return False
    video_signature = clips[0].video_signature()
    audio_signature = clips[0].audio_signature()
    return all(
        clip.video_signature() == video_signature
        and (not include_audio or clip.audio_signature() == audio_signature)
        for clip in clips[1:]
    )
