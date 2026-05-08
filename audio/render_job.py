from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from audio.bgm_config_utils import BgmRuntimeConfig
from audio.pipeline.segment_planner import Segment, VoiceTag


@dataclass(frozen=True)
class RuntimeContext:
    profile_dir: Optional[Path]
    profile_voice_defaults: Dict[str, str]
    runtime_config: BgmRuntimeConfig
    bgm_dir: Path


@dataclass(frozen=True)
class VoiceRuntimeMaps:
    voice_map_vi: Dict[VoiceTag, str]
    voice_map_en: Dict[VoiceTag, str]


@dataclass(frozen=True)
class RenderJobPaths:
    out_dir: Path
    wav_dir: Path
    out_file: Path
    srt_path: Path
    debug_json: Path


@dataclass(frozen=True)
class RenderJobArtifacts:
    segments: list[Segment]
    estimated_duration_seconds: float
    estimated_duration_hms: str
    debug_json: Optional[Path] = None
    wav_dir: Optional[Path] = None
    out_file: Optional[Path] = None
    srt_path: Optional[Path] = None
