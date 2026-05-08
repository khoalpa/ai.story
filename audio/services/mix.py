from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from audio.adapters.ffmpeg_audio_mixer import FfmpegMixConfig, ffmpeg_mix_audio
from audio.pipeline.segment_planner import Segment


@dataclass(frozen=True)
class MixRequest:
    segments: List[Segment]
    out_file: Path
    bgm_dir: Path
    mix_config: FfmpegMixConfig
    sample_rate: int = 48000
    audio_format: str = "wav"


def mix_audio_story(request: MixRequest, progress_callback: Optional[Callable[[dict], None]] = None) -> tuple[list[dict], Path]:
    return ffmpeg_mix_audio(
        segments=request.segments,
        out_file=request.out_file,
        bgm_dir=request.bgm_dir,
        sample_rate=request.sample_rate,
        mix_config=request.mix_config,
        audio_format=request.audio_format,
        progress_callback=progress_callback,
    )
