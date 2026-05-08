from __future__ import annotations

from audio.adapters.ffmpeg_audio_mixer import FfmpegMixConfig, format_hms
from audio.services.mix import MixRequest, mix_audio_story
from audio.render_events import (
    RenderEventSink,
    RenderPhaseCompletedEvent,
    RenderPhaseStartedEvent,
    emit_event,
    emit_render_event,
)
from audio.render_job import RenderJobArtifacts, RenderJobPaths, RuntimeContext, VoiceRuntimeMaps
from audio.services.render_script import estimate_audio_duration_seconds
from audio.pipeline.segment_planner import Segment
from audio.services.subtitle import write_srt_from_timeline
from audio.services.tts_render import TtsRenderConfig, render_tts_segments
from audio.adapters.tts_core import resolve_vieneu_model_name

BGM_FADE_IN_DEFAULT = 0.6
BGM_FADE_OUT_DEFAULT = 0.6


def build_mix_config(runtime_ctx: RuntimeContext, post_fx_preset: str, ffmpeg_exe: str, ffprobe_exe: str) -> FfmpegMixConfig:
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
    vieneu_core: str = "local",
    vieneu_mode: str = "standard",
    vieneu_api_base: str = "",
    vieneu_model_name: str = resolve_vieneu_model_name("", "standard"),
    vieneu_device: str = "cuda",
    vieneu_backend: str = "auto",
    vieneu_render_temperature: float = 0.7,
    vieneu_render_max_chars_chunk: int = 240,
    vieneu_render_use_batch: bool = False,
    vieneu_render_max_batch_size_run: int = 1,
) -> RenderJobArtifacts:
    paths.out_dir.mkdir(parents=True, exist_ok=True)
    paths.wav_dir.mkdir(parents=True, exist_ok=True)

    emit_render_event(
        event_sink,
        RenderPhaseStartedEvent(phase="tts", details={"wav_dir": paths.wav_dir, "segment_count": len(segments)}),
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
        ),
        progress_callback=lambda completed, total: emit_event(
            event_sink,
            "render.phase.progress",
            phase="tts",
            completed=completed,
            total=total,
            unit="segments",
            percent=int(completed * 100 / max(1, total)) if total else 100,
        ),
    )

    emit_render_event(
        event_sink,
        RenderPhaseCompletedEvent(phase="tts", details={"wav_dir": paths.wav_dir, "segment_count": len(segments)}),
    )

    emit_render_event(
        event_sink,
        RenderPhaseStartedEvent(phase="mix", details={"out_file": paths.out_file, "bgm_dir": runtime_ctx.bgm_dir}),
    )
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
            ),
            audio_format=audio_format,
        ),
        progress_callback=lambda data: emit_event(event_sink, "render.phase.progress", phase="mix", **data),
    )
    emit_render_event(
        event_sink,
        RenderPhaseCompletedEvent(phase="mix", details={"out_file": final_out_file}),
    )

    emit_render_event(
        event_sink,
        RenderPhaseStartedEvent(phase="subtitle", details={"srt_path": paths.srt_path}),
    )
    write_srt_from_timeline(timeline, paths.srt_path)
    emit_render_event(
        event_sink,
        RenderPhaseCompletedEvent(phase="subtitle", details={"srt_path": paths.srt_path}),
    )

    est_seconds = estimate_audio_duration_seconds(segments)
    return RenderJobArtifacts(
        segments=segments,
        estimated_duration_seconds=est_seconds,
        estimated_duration_hms=format_hms(est_seconds),
        wav_dir=paths.wav_dir,
        out_file=final_out_file,
        srt_path=paths.srt_path,
    )
