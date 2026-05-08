from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from audio.adapters.ffmpeg_audio_mixer import format_hms
from audio.pipeline.plain_script_parser import normalize_bgm_name
from audio.render_job import RenderJobArtifacts, RuntimeContext
from audio.pipeline.script_pipeline import plan_segments_from_plain_script
from audio.pipeline.segment_planner import (
    Segment,
    apply_sentiment_tone,
    auto_assign_bgm_for_zones,
    base_chars_per_second_for_voice,
    rate_str_to_factor,
)


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save_segments_debug_json(segments: list[Segment], path: Path) -> None:
    data = [
        {
            "idx": i,
            "text": seg.text,
            "voice": seg.voice,
            "rate": seg.rate,
            "bgm": seg.bgm,
            "bgm_gain_db": seg.bgm_gain_db,
            "ambience": seg.ambience,
            "ambience_gain_db": seg.ambience_gain_db,
            "pause_ms_before": seg.pause_ms_before,
            "zone": seg.zone,
            "lang": seg.lang,
            "lang_from_tag": seg.lang_from_tag,
            "emotion": seg.emotion,
            "env": seg.env,
        }
        for i, seg in enumerate(segments)
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def estimate_audio_duration_seconds(segments: list[Segment]) -> float:
    total = 0.0
    min_segment_seconds = 0.8
    max_segment_seconds = 25.0

    for seg in segments:
        if seg.pause_ms_before > 0:
            total += seg.pause_ms_before / 1000.0

        clean_text = seg.text.strip("-–—*_ .·").strip()
        if not clean_text:
            continue

        num_chars = len(clean_text)
        planner_factor = rate_str_to_factor(seg.rate)
        chars_per_second = base_chars_per_second_for_voice(seg.voice) * planner_factor
        chars_per_second = min(30.0, max(6.0, chars_per_second))
        speech_seconds = num_chars / chars_per_second
        speech_seconds = min(max_segment_seconds, max(min_segment_seconds, speech_seconds))
        total += speech_seconds

    return total


def parse_script_to_segments(full_text: str, *, voice_rate_map: dict[str, object] | None = None) -> list[Segment]:
    return plan_segments_from_plain_script(full_text, voice_rate_map=voice_rate_map)


def prepare_segments(full_text: str, *, bgm_fallback: Optional[str], runtime_ctx: RuntimeContext, sentiment_tone: bool = False, voice_rate_map: dict[str, object] | None = None) -> RenderJobArtifacts:
    segments = parse_script_to_segments(full_text, voice_rate_map=voice_rate_map)
    auto_assign_bgm_for_zones(
        segments,
        normalize_bgm_name(bgm_fallback),
        runtime_config=runtime_ctx.runtime_config,
    )
    if sentiment_tone:
        apply_sentiment_tone(segments, voice_rate_map=voice_rate_map)

    est_seconds = estimate_audio_duration_seconds(segments)
    return RenderJobArtifacts(
        segments=segments,
        estimated_duration_seconds=est_seconds,
        estimated_duration_hms=format_hms(est_seconds),
    )
