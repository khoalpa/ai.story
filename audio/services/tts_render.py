from __future__ import annotations

import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from audio.adapters.edge_tts import render_tts_all as render_tts_all_edge
from audio.adapters.tts_core import (
    apply_vieneu_time_stretch,
    get_vieneu_engine,
    resolve_vieneu_effective_mode,
    resolve_vieneu_model_for_runtime,
    resolve_vieneu_model_name,
    resolve_vieneu_runtime_backend,
    resolve_vieneu_runtime_device,
    resolve_vieneu_segment_voice,
)
from audio.adapters.vieneu_tts import synthesize_segment_with_vieneu_async
from audio.exceptions import TtsError, UnsupportedTtsProviderError
from audio.logging_utils import get_logger
from audio.pipeline.segment_planner import Segment, VoiceTag
from audio.render_events import (
    RenderEventSink,
    RenderProviderFallbackEvent,
    emit_event,
    emit_render_event,
)
from audio.services.tts_cache import TtsCacheSession, build_segment_cache_key
from audio.tts_provider import (
    DEFAULT_TTS_PROVIDER,
    TTS_PROVIDER_EDGE,
    TTS_PROVIDER_VIENEU,
    normalize_tts_provider,
)

logger = get_logger(__name__)


def resolve_tts_concurrency(
    provider: str,
    requested: int,
    *,
    vieneu_device: str = "cuda",
    vieneu_mode: str = "standard",
    vieneu_use_batch: bool = False,
) -> int:
    """Resolve a conservative provider-aware concurrency limit."""
    limit = max(1, int(requested or 1))
    if normalize_tts_provider(provider) != TTS_PROVIDER_VIENEU:
        return limit
    if str(vieneu_mode or "").strip().lower() == "remote":
        return min(limit, 8)
    if vieneu_use_batch:
        return 1
    if str(vieneu_device or "cuda").strip().lower() in {"cuda", "auto"}:
        return min(limit, 2)
    return min(limit, 4)


@dataclass(frozen=True)
class TtsRenderConfig:
    wav_dir: Path
    voice_map_vi: Dict[VoiceTag, str]
    voice_map_en: Dict[VoiceTag, str]
    abbr_map: Dict[str, str]
    auto_en_lines: bool = False
    max_concurrent_tts: int = 8
    tts_provider: str = DEFAULT_TTS_PROVIDER
    vieneu_core: str = "local"
    vieneu_mode: str = "standard"
    vieneu_api_base: str | None = None
    vieneu_model_name: str | None = None
    vieneu_device: str = "cuda"
    vieneu_backend: str = "auto"
    vieneu_render_temperature: float = 0.7
    vieneu_render_max_chars_chunk: int = 240
    vieneu_render_use_batch: bool = True
    vieneu_render_max_batch_size_run: int = 4
    ffmpeg_exe: str = "ffmpeg"
    event_sink: RenderEventSink | None = None
    cache_enabled: bool = True
    cache_dir: Path | None = None


def _cache_settings(config: TtsRenderConfig, provider: str) -> dict[str, object]:
    common: dict[str, object] = {
        "auto_en_lines": bool(config.auto_en_lines),
        "abbr_map": dict(config.abbr_map),
    }
    if provider == TTS_PROVIDER_VIENEU:
        common.update(
            {
                "core": config.vieneu_core,
                "mode": config.vieneu_mode,
                "api_base": str(config.vieneu_api_base or ""),
                "model": str(config.vieneu_model_name or ""),
                "device": config.vieneu_device,
                "backend": config.vieneu_backend,
                "temperature": float(config.vieneu_render_temperature),
                "max_chars": int(config.vieneu_render_max_chars_chunk),
            }
        )
    return common


def _build_cache_session(segments: list[Segment], config: TtsRenderConfig, provider: str) -> TtsCacheSession:
    settings = _cache_settings(config, provider)
    keys = [
        build_segment_cache_key(
            segment,
            provider=provider,
            voice_map_vi=config.voice_map_vi,
            voice_map_en=config.voice_map_en,
            settings=settings,
        )
        for segment in segments
    ]
    return TtsCacheSession(
        wav_dir=config.wav_dir,
        cache_dir=config.cache_dir,
        keys=keys,
        enabled=config.cache_enabled,
    )


async def render_tts_segments_async(segments: list[Segment], config: TtsRenderConfig, progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
    config.wav_dir.mkdir(parents=True, exist_ok=True)
    provider = normalize_tts_provider(config.tts_provider)
    cache = _build_cache_session(segments, config, provider)
    restored = cache.restore() if segments else None
    miss_indices = list(restored.misses) if restored is not None else []
    if restored is not None:
        emit_event(
            config.event_sink,
            "render.tts.cache.resolved",
            enabled=bool(config.cache_enabled),
            cache_dir=cache.cache_dir,
            hit_count=len(restored.hits),
            miss_count=len(restored.misses),
            segment_count=len(segments),
        )
        if progress_callback and restored.hits:
            progress_callback(len(restored.hits), len(segments))
        if not miss_indices:
            return
    if provider == TTS_PROVIDER_EDGE:
        missing_segments = [segments[index] for index in miss_indices]
        await render_tts_all_edge(
            segments=missing_segments,
            wav_dir=config.wav_dir,
            voice_map_vi=config.voice_map_vi,
            voice_map_en=config.voice_map_en,
            abbr_map=config.abbr_map,
            auto_en_lines=config.auto_en_lines,
            max_concurrent_tts=config.max_concurrent_tts,
            progress_callback=(
                lambda completed, _total: progress_callback(len(restored.hits) + completed, len(segments))
                if progress_callback
                else None
            ),
            output_indices=miss_indices,
            segment_completed_callback=lambda index, _path: cache.commit(index),
        )
        return
    if provider == TTS_PROVIDER_VIENEU:
        runtime_device = resolve_vieneu_runtime_device(config.vieneu_device)
        effective_mode = resolve_vieneu_effective_mode(
            config.vieneu_core,
            config.vieneu_mode,
            runtime_device,
            config.vieneu_model_name,
        )
        runtime_model_name = resolve_vieneu_model_for_runtime(
            resolve_vieneu_model_name(config.vieneu_model_name, effective_mode),
            effective_mode,
            allow_network=False,
        )
        runtime_backend = resolve_vieneu_runtime_backend(
            effective_mode,
            runtime_model_name,
            runtime_device,
            config.vieneu_backend,
        )
        engine = get_vieneu_engine(
            mode=effective_mode,
            api_base=str(config.vieneu_api_base or ""),
            model_name=runtime_model_name,
            device=runtime_device,
            backend=runtime_backend,
        )
        total = len(segments)
        if total <= 0:
            if progress_callback:
                progress_callback(0, 0)
            return

        def _call_vieneu_infer_batch(
            batch_texts: list[str],
            batch_voices: list[object | None],
            batch_voice_ids: list[str],
        ) -> list[object]:
            infer_batch = getattr(engine, "infer_batch", None)
            if not callable(infer_batch):
                raise AttributeError("VieNeu engine does not expose infer_batch")

            max_chars = max(1, int(config.vieneu_render_max_chars_chunk))
            temperature = float(config.vieneu_render_temperature)
            try:
                signature = inspect.signature(infer_batch)
            except (TypeError, ValueError):
                signature = None

            candidates: list[tuple[tuple[str, object], ...]] = []
            voice_values = [voice for voice in batch_voices if voice is not None]
            any_voice = bool(voice_values)
            all_have_voice = len(voice_values) == len(batch_voices)
            voice_ids = [voice_id for voice_id in batch_voice_ids if voice_id]
            same_voice = len(set(voice_ids)) == 1 if voice_ids else False
            if signature is not None:
                params = signature.parameters
                if "texts" in params:
                    payload: list[tuple[str, object]] = [("texts", batch_texts)]
                elif "text" in params:
                    payload = [("text", batch_texts)]
                else:
                    payload = []
                if payload:
                    if any_voice:
                        if all_have_voice and same_voice and "voice" in params:
                            payload.append(("voice", next(voice for voice in voice_values)))
                        elif all_have_voice and not same_voice and "voices" in params:
                            payload.append(("voices", batch_voices))
                        else:
                            payload = []
                    if "temperature" in params:
                        payload.append(("temperature", temperature))
                    if "max_chars" in params:
                        payload.append(("max_chars", max_chars))
                    if "max_chars_chunk" in params:
                        payload.append(("max_chars_chunk", max_chars))
                    if payload:
                        candidates.append(tuple(payload))

            if not candidates:
                if all_have_voice and same_voice:
                    first_voice = next((voice for voice in voice_values if voice is not None), None)
                    candidates = [
                        (("texts", batch_texts), ("voice", first_voice), ("temperature", temperature), ("max_chars", max_chars)),
                    ]
                elif all_have_voice and not same_voice:
                    candidates = [
                        (("texts", batch_texts), ("voices", batch_voices), ("temperature", temperature), ("max_chars", max_chars)),
                    ]
                elif any_voice:
                    raise TtsError("VieNeu infer_batch requires voice-aware support for mixed or preset voices")
                else:
                    candidates = [
                        (("texts", batch_texts), ("temperature", temperature), ("max_chars", max_chars)),
                        (("text", batch_texts), ("temperature", temperature), ("max_chars", max_chars)),
                        (("texts", batch_texts),),
                        (("text", batch_texts),),
                    ]

            last_exc: Exception | None = None
            for payload in candidates:
                kwargs = {key: value for key, value in payload}
                try:
                    result = infer_batch(**kwargs)
                    if isinstance(result, list):
                        return result
                    return list(result)
                except TypeError as exc:
                    last_exc = exc
                    continue
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("VieNeu infer_batch did not return any audio")

        def _render_batch(batch_items: list[tuple[int, Segment, str, object | None]]) -> None:
            batch_texts = [str(seg.text or "").strip() for _idx, seg, _voice_id, _voice in batch_items]
            batch_voice_ids = [voice_id for _idx, _seg, voice_id, _voice in batch_items]
            batch_voices = [voice for _idx, _seg, _voice_id, voice in batch_items]
            batch_outputs = _call_vieneu_infer_batch(batch_texts, batch_voices, batch_voice_ids)
            if len(batch_outputs) != len(batch_items):
                raise RuntimeError(
                    f"VieNeu infer_batch returned {len(batch_outputs)} outputs for {len(batch_items)} inputs"
                )
            stretch_jobs: list[tuple[Path, str]] = []
            for (idx, _seg, _voice_id, _voice), audio in zip(batch_items, batch_outputs, strict=True):
                out_wav = config.wav_dir / f"seg_{idx:03d}.wav"
                engine.save(audio, out_wav)
                stretch_jobs.append((out_wav, str(_seg.rate or "0%")))
            if stretch_jobs:
                with ThreadPoolExecutor(max_workers=min(4, len(stretch_jobs))) as executor:
                    list(executor.map(
                        lambda item: apply_vieneu_time_stretch(
                            item[0], rate=item[1], ffmpeg_exe=config.ffmpeg_exe
                        ),
                        stretch_jobs,
                    ))

        batch_size = max(1, min(int(config.vieneu_render_max_batch_size_run or 1), total))
        can_batch = bool(config.vieneu_render_use_batch) and effective_mode == "standard" and hasattr(engine, "infer_batch")
        concurrency = min(
            resolve_tts_concurrency(
                provider,
                config.max_concurrent_tts,
                vieneu_device=runtime_device,
                vieneu_mode=effective_mode,
                vieneu_use_batch=can_batch,
            ),
            total,
        )
        emit_event(
            config.event_sink,
            "render.tts.runtime.resolved",
            provider=provider,
            requested_concurrency=max(1, int(config.max_concurrent_tts or 1)),
            effective_concurrency=concurrency,
            device=runtime_device,
            mode=effective_mode,
            batch_enabled=can_batch,
            batch_size=batch_size if can_batch else 1,
            segment_count=total,
        )
        if can_batch:
            done = 0
            try:
                if progress_callback:
                    progress_callback(0, total)
                batch_items: list[tuple[int, Segment, str, object | None]] = []
                for idx in miss_indices:
                    seg = segments[idx]
                    voice_id, voice = resolve_vieneu_segment_voice(engine, seg, config.voice_map_vi, config.voice_map_en)
                    batch_items.append((idx, seg, voice_id, voice))
                    if len(batch_items) >= batch_size:
                        await asyncio.to_thread(_render_batch, batch_items)
                        done += len(batch_items)
                        for completed_idx, *_rest in batch_items:
                            cache.commit(completed_idx)
                        batch_items = []
                        if progress_callback:
                            progress_callback(len(restored.hits) + done, total)
                if batch_items:
                    await asyncio.to_thread(_render_batch, batch_items)
                    done += len(batch_items)
                    for completed_idx, *_rest in batch_items:
                        cache.commit(completed_idx)
                    if progress_callback:
                        progress_callback(len(restored.hits) + done, total)
                return
            except Exception as exc:
                logger.warning(
                    "VieNeu batch rendering failed; falling back to per-segment rendering: %s",
                    exc,
                    exc_info=True,
                )
                emit_render_event(
                    config.event_sink,
                    RenderProviderFallbackEvent(
                        provider="vieneu",
                        from_mode="batch",
                        to_mode="per_segment",
                        reason=str(exc),
                    ),
                )

        sem = asyncio.Semaphore(concurrency)
        progress_lock = asyncio.Lock()
        done = 0

        async def process_one(idx: int, seg: Segment) -> None:
            nonlocal done
            out_wav = config.wav_dir / f"seg_{idx:03d}.wav"
            async with sem:
                await synthesize_segment_with_vieneu_async(
                    seg,
                    out_wav,
                    config.voice_map_vi,
                    config.voice_map_en,
                    auto_en_lines=config.auto_en_lines,
                    vieneu_mode=effective_mode,
                    vieneu_api_base=str(config.vieneu_api_base or ""),
                    vieneu_model_name=runtime_model_name,
                    vieneu_device=runtime_device,
                    backend=runtime_backend,
                    vieneu_temperature=float(config.vieneu_render_temperature),
                    vieneu_max_chars_chunk=int(config.vieneu_render_max_chars_chunk),
                    vieneu_use_batch=bool(config.vieneu_render_use_batch),
                    vieneu_max_batch_size_run=int(config.vieneu_render_max_batch_size_run),
                    ffmpeg_exe=config.ffmpeg_exe,
                )
            async with progress_lock:
                cache.commit(idx)
                done += 1
                if progress_callback:
                    progress_callback(len(restored.hits) + done, total)

        if progress_callback:
            progress_callback(0, total)
        await asyncio.gather(*(process_one(i, segments[i]) for i in miss_indices))
        return
    raise UnsupportedTtsProviderError(f"Unsupported TTS provider: {config.tts_provider}")


def render_tts_segments(segments: list[Segment], config: TtsRenderConfig, progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
    asyncio.run(render_tts_segments_async(segments, config, progress_callback=progress_callback))
