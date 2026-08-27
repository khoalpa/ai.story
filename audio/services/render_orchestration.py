from __future__ import annotations

from time import perf_counter

from audio.adapters.ffmpeg_audio_mixer import FfmpegMixConfig, format_hms
from audio.adapters.tts_core import resolve_vieneu_model_name
from audio.adapters.wav_analysis import get_wav_duration_seconds
from audio.pipeline.segment_planner import Segment
from audio.render_events import (
    RenderEventSink,
    RenderPhaseCompletedEvent,
    RenderPhaseStartedEvent,
    emit_event,
    emit_render_event,
)
from audio.render_job import (
    RenderJobArtifacts,
    RenderJobPaths,
    RuntimeContext,
    VoiceRuntimeMaps,
)
from audio.services.mix import MixRequest, mix_audio_story
from audio.services.render_script import estimate_audio_duration_seconds
from audio.services.subtitle import write_srt_from_timeline
from audio.services.tts_render import TtsRenderConfig, render_tts_segments

BGM_FADE_IN_DEFAULT = 0.6
BGM_FADE_OUT_DEFAULT = 0.6


class _GeneratedWavDurationTracker:
    """Incrementally total completed segment WAVs without re-reading old files."""

    def __init__(self, wav_dir, segment_count: int) -> None:
        self.wav_dir = wav_dir
        self.segment_count = max(0, int(segment_count))
        self._measured: set[int] = set()
        self.total_seconds = 0.0

    def refresh(self) -> float:
        for wav_path in self.wav_dir.glob("seg_*.wav"):
            try:
                index = int(wav_path.stem.removeprefix("seg_"))
            except ValueError:
                continue
            if index < 0 or index >= self.segment_count:
                continue
            if index in self._measured:
                continue
            duration = get_wav_duration_seconds(wav_path)
            if duration is None:
                continue
            self._measured.add(index)
            self.total_seconds += duration
        return self.total_seconds


def build_mix_config(
    runtime_ctx: RuntimeContext,
    post_fx_preset: str,
    ffmpeg_exe: str,
    ffprobe_exe: str,
    *,
    loudness_profile: str = "narration",
    output_channels: int = 2,
    mp3_bitrate_kbps: int = 192,
    quality_gate: bool = True,
    pacing_preset: str = "natural",
) -> FfmpegMixConfig:
    return FfmpegMixConfig(
        ffmpeg_exe=ffmpeg_exe,
        ffprobe_exe=ffprobe_exe,
        intro_clip_file=runtime_ctx.runtime_config.intro_clip.get("file", "") if runtime_ctx.runtime_config.intro_clip else "",
        intro_clip_gain_db=float(runtime_ctx.runtime_config.intro_clip.get("gain_db", 0.0)) if runtime_ctx.runtime_config.intro_clip else 0.0,
        outro_clip_file=runtime_ctx.runtime_config.outro_clip.get("file", "") if runtime_ctx.runtime_config.outro_clip else "",
        outro_clip_gain_db=float(runtime_ctx.runtime_config.outro_clip.get("gain_db", 0.0)) if runtime_ctx.runtime_config.outro_clip else 0.0,
        bgm_fade_in_default=BGM_FADE_IN_DEFAULT,
        bgm_fade_out_default=BGM_FADE_OUT_DEFAULT,
        post_fx_preset=post_fx_preset,
        loudness_profile=loudness_profile,
        output_channels=output_channels,
        mp3_bitrate_kbps=mp3_bitrate_kbps,
        quality_gate=quality_gate,
        pacing_preset=pacing_preset,
    )


def run_render_job(
    *,
    segments: list[Segment],
    paths: RenderJobPaths,
    runtime_ctx: RuntimeContext,
    voice_maps: VoiceRuntimeMaps,
    voice_rate_map: dict[str, str] | None = None,
    abbr_map: dict[str, str],
    auto_en_lines: bool,
    max_concurrent_tts: int,
    tts_provider: str,
    post_fx_preset: str,
    ffmpeg_exe: str,
    ffprobe_exe: str,
    event_sink: RenderEventSink | None = None,
    audio_format: str = "wav",
    loudness_profile: str = "narration",
    output_channels: int = 2,
    mp3_bitrate_kbps: int = 192,
    quality_gate: bool = True,
    pacing_preset: str = "natural",
    vieneu_core: str = "local",
    vieneu_mode: str = "standard",
    vieneu_api_base: str = "",
    vieneu_model_name: str = resolve_vieneu_model_name("", "standard"),
    vieneu_device: str = "cuda",
    vieneu_backend: str = "auto",
    vieneu_render_temperature: float = 0.7,
    vieneu_render_max_chars_chunk: int = 240,
    vieneu_render_use_batch: bool = True,
    vieneu_render_max_batch_size_run: int = 4,
) -> RenderJobArtifacts:
    paths.out_dir.mkdir(parents=True, exist_ok=True)
    paths.wav_dir.mkdir(parents=True, exist_ok=True)

    estimated_audio_seconds = estimate_audio_duration_seconds(segments)
    job_started_at = perf_counter()
    emit_render_event(
        event_sink,
        RenderPhaseStartedEvent(phase="tts", details={"wav_dir": paths.wav_dir, "segment_count": len(segments)}),
    )
    tts_started_at = perf_counter()
    generated_duration = _GeneratedWavDurationTracker(paths.wav_dir, len(segments))

    def report_tts_progress(completed: int, total: int) -> None:
        emit_event(
            event_sink,
            "render.phase.progress",
            phase="tts",
            completed=completed,
            total=total,
            unit="segments",
            percent=int(completed * 100 / max(1, total)) if total else 100,
            actual_audio_seconds=round(generated_duration.refresh(), 3),
        )

    render_tts_segments(
        segments,
        TtsRenderConfig(
            wav_dir=paths.wav_dir,
            voice_map_vi=voice_maps.voice_map_vi,
            voice_map_en=voice_maps.voice_map_en,
            abbr_map=abbr_map,
            auto_en_lines=auto_en_lines,
            max_concurrent_tts=max_concurrent_tts,
            tts_provider=tts_provider,
            vieneu_core=vieneu_core,
            vieneu_mode=vieneu_mode,
            vieneu_api_base=vieneu_api_base,
            vieneu_model_name=vieneu_model_name,
            vieneu_device=vieneu_device,
            vieneu_backend=vieneu_backend,
            vieneu_render_temperature=vieneu_render_temperature,
            vieneu_render_max_chars_chunk=vieneu_render_max_chars_chunk,
            vieneu_render_use_batch=vieneu_render_use_batch,
            vieneu_render_max_batch_size_run=vieneu_render_max_batch_size_run,
            ffmpeg_exe=ffmpeg_exe,
            event_sink=event_sink,
        ),
        progress_callback=report_tts_progress,
    )

    tts_elapsed_seconds = perf_counter() - tts_started_at
    emit_render_event(
        event_sink,
        RenderPhaseCompletedEvent(
            phase="tts",
            details={
                "wav_dir": paths.wav_dir,
                "segment_count": len(segments),
                "elapsed_ms": round(tts_elapsed_seconds * 1000, 3),
                "segments_per_second": round(len(segments) / max(tts_elapsed_seconds, 1e-9), 4),
                "realtime_factor": round(tts_elapsed_seconds / max(estimated_audio_seconds, 1e-9), 4),
            },
        ),
    )

    emit_render_event(
        event_sink,
        RenderPhaseStartedEvent(phase="mix", details={"out_file": paths.out_file, "bgm_dir": runtime_ctx.bgm_dir}),
    )
    mix_started_at = perf_counter()
    timeline, final_out_file = mix_audio_story(
        MixRequest(
            segments=segments,
            out_file=paths.out_file,
            bgm_dir=runtime_ctx.bgm_dir,
            mix_config=build_mix_config(
                runtime_ctx=runtime_ctx,
                post_fx_preset=post_fx_preset,
                ffmpeg_exe=ffmpeg_exe,
                ffprobe_exe=ffprobe_exe,
                loudness_profile=loudness_profile,
                output_channels=output_channels,
                mp3_bitrate_kbps=mp3_bitrate_kbps,
                quality_gate=quality_gate,
                pacing_preset=pacing_preset,
            ),
            audio_format=audio_format,
        ),
        progress_callback=lambda data: emit_event(event_sink, "render.phase.progress", phase="mix", **data),
    )
    mix_elapsed_seconds = perf_counter() - mix_started_at
    emit_render_event(
        event_sink,
        RenderPhaseCompletedEvent(
            phase="mix",
            details={
                "out_file": final_out_file,
                "elapsed_ms": round(mix_elapsed_seconds * 1000, 3),
                "realtime_factor": round(mix_elapsed_seconds / max(estimated_audio_seconds, 1e-9), 4),
            },
        ),
    )

    emit_render_event(
        event_sink,
        RenderPhaseStartedEvent(phase="subtitle", details={"srt_path": paths.srt_path}),
    )
    subtitle_started_at = perf_counter()
    write_srt_from_timeline(timeline, paths.srt_path)
    subtitle_elapsed_seconds = perf_counter() - subtitle_started_at
    emit_render_event(
        event_sink,
        RenderPhaseCompletedEvent(
            phase="subtitle",
            details={"srt_path": paths.srt_path, "elapsed_ms": round(subtitle_elapsed_seconds * 1000, 3)},
        ),
    )

    total_elapsed_seconds = perf_counter() - job_started_at
    emit_event(
        event_sink,
        "render.telemetry.completed",
        elapsed_ms=round(total_elapsed_seconds * 1000, 3),
        estimated_audio_seconds=round(estimated_audio_seconds, 3),
        realtime_factor=round(total_elapsed_seconds / max(estimated_audio_seconds, 1e-9), 4),
        segment_count=len(segments),
    )
    return RenderJobArtifacts(
        segments=segments,
        estimated_duration_seconds=estimated_audio_seconds,
        estimated_duration_hms=format_hms(estimated_audio_seconds),
        wav_dir=paths.wav_dir,
        out_file=final_out_file,
        srt_path=paths.srt_path,
        quality_report=(
            final_out_file.with_name(f"{final_out_file.stem}.audio_quality.json")
            if quality_gate
            else None
        ),
    )
