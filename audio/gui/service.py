from __future__ import annotations

import asyncio
import hashlib
import tempfile
from pathlib import Path
from typing import Any

from audio.env_runtime import bootstrap_vieneu_runtime
from audio.exceptions import (
    AssetProfileError,
    AudioStoryError,
    DependencyError,
    FfmpegDependencyError,
    RuntimePathError,
    TtsDependencyError,
    TtsNetworkError,
    UnsupportedTtsProviderError,
)
from audio.render_audio_app import run_render_audio_app, validate_only_script
from audio.render_job_repository import JobRepository
from audio.pipeline.segment_planner import Segment
from audio.tts_provider import TTS_PROVIDER_EDGE, TTS_PROVIDER_VIENEU, normalize_tts_provider
from audio.adapters.edge_tts import tts_segment_to_file
from audio.adapters.tts_core import (
    DEFAULT_VIENEU_API_BASE,
    DEFAULT_VIENEU_DEVICE,
    DEFAULT_VIENEU_MODEL_NAME,
    clear_vieneu_runtime_caches,
    list_vieneu_preset_voices,
    normalize_vieneu_mode,
    resolve_vieneu_model_for_runtime,
    resolve_vieneu_model_name,
    resolve_vieneu_runtime_device,
    resolve_vieneu_runtime_backend,
    resolve_vieneu_effective_mode,
    synthesize_segment_with_vieneu,
    validate_vieneu_mode_model_compatibility,
)
from audio.voice_catalog import get_voice_choices

from .helpers import make_request, summarize_result, write_plain_script_to_temp


def _resolve_vieneu_device_for_runtime(value: object) -> str:
    return resolve_vieneu_runtime_device(value or DEFAULT_VIENEU_DEVICE)


def format_runtime_error(exc: Exception) -> str:
    if isinstance(exc, UnsupportedTtsProviderError):
        return f"Unsupported TTS provider: {exc}\nSuggestion: choose edge or vieneu in settings."
    if isinstance(exc, (FfmpegDependencyError, DependencyError, TtsDependencyError)):
        return f"Missing runtime dependency: {exc}\nSuggestion: check ffmpeg/ffprobe, edge-tts, vieneu, and PATH."
    if isinstance(exc, AssetProfileError):
        return f"Invalid asset profile: {exc}\nSuggestion: check the profile folder, manifest.json, and related asset files."
    if isinstance(exc, RuntimePathError):
        return f"Invalid runtime path: {exc}\nSuggestion: check the input file, output directory, bgm dir, and abbreviation map."
    if isinstance(exc, TtsNetworkError):
        return f"TTS render failed due to network or TTS service issues: {exc}\nSuggestion: retry when the network is stable or reduce max concurrent TTS."
    return f"Pipeline run failed: {exc}"


def run_audio_job(*, plain_text: str, settings: dict[str, Any], repository: JobRepository, event_sink=None):  # noqa: ARG001
    with tempfile.TemporaryDirectory(prefix="render_audio_gui_") as tmp:
        work_dir = Path(tmp)
        output_dir = Path(settings["output_dir"])
        input_path = write_plain_script_to_temp(plain_text, work_dir)
        request = make_request(input_path=input_path, output_dir=output_dir, settings=settings)
        result = run_render_audio_app(
            request,
            ffmpeg_exe=settings["ffmpeg_exe"],
            ffprobe_exe=settings["ffprobe_exe"],
            event_sink=event_sink,
        )
    return result


def summarize_audio_job(result) -> dict[str, Any]:
    return summarize_result(result)


def validate_plain_text(plain_text: str) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    with tempfile.TemporaryDirectory(prefix="render_audio_validate_") as tmp:
        tmp_path = Path(tmp) / "story.txt"
        tmp_path.write_text(plain_text, encoding="utf-8")
        result = validate_only_script(tmp_path)

        if isinstance(result, tuple):
            if len(result) == 3:
                a, b, c = result
                if isinstance(c, int):
                    return c, tuple(b or ()), ()
                return a, tuple(b or ()), tuple(c or ())
            raise ValueError(f"Unexpected validation result tuple shape: {result!r}")

        return result.exit_code, tuple(result.errors), tuple(getattr(result, "warnings", ()))


def normalize_vieneu_core(value: object) -> str:
    normalized = str(value or "local").strip().lower().replace("-", "_").replace(" ", "_")
    return "remote_api" if normalized in {"remote", "remote_api", "api", "remoteapi"} else "local"


def resolve_vieneu_ui_mode(core: object, mode: object, device: object | None = None) -> str:
    return resolve_vieneu_effective_mode(core, mode, device)


def resolve_vieneu_runtime_mode(core: object, mode: object, device: object | None = None) -> str:
    return resolve_vieneu_effective_mode(core, mode, device)


def describe_vieneu_cuda_turbo_path(*, core: object, mode: object, device: object | None = None) -> str:
    selected_core = normalize_vieneu_core(core)
    selected_mode = normalize_vieneu_mode(mode)
    selected_device = _resolve_vieneu_device_for_runtime(device)
    if selected_core != "local" or selected_device != "cuda":
        return ""
    return (
        "VieNeu local + cuda is auto-promoted to Standard so the GPU path is used. "
        "VieNeu Turbo is documented upstream as a CPU/edge-oriented path, so cuda + turbo can still "
        "be misleading if you expect guaranteed GPU acceleration."
    )


def get_vieneu_runtime_model_details(settings: dict[str, Any], *, allow_network: bool = False) -> dict[str, str]:
    core = normalize_vieneu_core(settings.get("vieneu_core"))
    mode = normalize_vieneu_mode(settings.get("vieneu_mode"))
    device = _resolve_vieneu_device_for_runtime(settings.get("vieneu_device"))
    backend = str(settings.get("vieneu_backend") or "auto").strip().lower()
    runtime_mode = resolve_vieneu_runtime_mode(core, mode, device)
    effective_backend = resolve_vieneu_runtime_backend(runtime_mode, settings.get("vieneu_model_name"), device, backend)
    api_base = str(settings.get("vieneu_api_base") or DEFAULT_VIENEU_API_BASE).strip()
    configured_model = resolve_vieneu_model_name(settings.get("vieneu_model_name"), mode)
    runtime_model = configured_model
    warning = describe_vieneu_cuda_turbo_path(core=core, mode=mode, device=device)
    if backend and backend != "auto" and backend != effective_backend:
        backend_warning = f"Requested backend {backend!r} fell back to {effective_backend!r} for the selected model/device."
        warning = backend_warning if not warning else f"{warning} {backend_warning}"
    try:
        runtime_model = resolve_vieneu_model_for_runtime(configured_model, runtime_mode, allow_network=allow_network)
    except Exception as exc:
        if core == "local" and runtime_mode == "standard" and mode == "turbo" and device == "cuda":
            configured_model = resolve_vieneu_model_name("", runtime_mode)
            runtime_model = resolve_vieneu_model_for_runtime(configured_model, runtime_mode, allow_network=allow_network)
        else:
            warning = str(exc) if not warning else f"{warning} {exc}"
    return {
        "core": core,
        "mode": mode,
        "runtime_mode": runtime_mode,
        "backend": effective_backend,
        "backend_requested": backend or "auto",
        "device": device,
        "api_base": api_base,
        "configured_model": configured_model,
        "runtime_model": runtime_model,
        "warning": warning,
    }


def _get_vieneu_preview_config(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature": float(settings.get("vieneu_preview_temperature", 0.6) or 0.6),
        "max_chars_chunk": int(float(settings.get("vieneu_preview_max_chars_chunk", 160) or 160)),
        "use_batch": bool(settings.get("vieneu_preview_use_batch", False)),
        "max_batch_size_run": int(float(settings.get("vieneu_preview_max_batch_size_run", 1) or 1)),
        "text_max_len": int(float(settings.get("vieneu_preview_text_max_len", 100) or 100)),
    }


def _get_vieneu_render_config(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature": float(settings.get("vieneu_render_temperature", 0.7) or 0.7),
        "max_chars_chunk": int(float(settings.get("vieneu_render_max_chars_chunk", 240) or 240)),
        "use_batch": bool(settings.get("vieneu_render_use_batch", False)),
        "max_batch_size_run": int(float(settings.get("vieneu_render_max_batch_size_run", 1) or 1)),
    }


def _preview_voice_role(provider: str, lang: str, selected_voice: str) -> str:
    candidate = str(selected_voice or "").strip()
    if not candidate:
        return "narrator"
    for role in ("narrator", "female", "male"):
        choices = get_voice_choices(tts_provider=provider, lang=lang, role=role)
        if any(str(item.value or "").strip() == candidate for item in choices):
            return role
    return "narrator"


def _preview_voice_speed_key(lang: str, role: str) -> str:
    normalized_lang = str(lang or "vi").strip().lower()
    normalized_role = str(role or "narrator").strip().lower()
    prefix = "voice_en" if normalized_lang == "en" else "voice"
    if normalized_role not in {"narrator", "female", "male"}:
        normalized_role = "narrator"
    return f"{prefix}_{normalized_role}_speed"


def _preview_voice_rate(settings: dict[str, Any], lang: str, role: str) -> str:
    key = _preview_voice_speed_key(lang, role)
    default_value = 12
    raw_speed = settings.get(key, default_value)
    try:
        speed = int(raw_speed)
    except (TypeError, ValueError):
        speed = default_value
    return f"{speed:+d}%" if speed else "0%"


def _preview_tts_cache_key(
    *,
    provider: str,
    safe_lang: str,
    selected_voice: str,
    preview_text: str,
    settings: dict[str, Any],
) -> str:
    preview_cfg = _get_vieneu_preview_config(settings)
    preview_role = _preview_voice_role(provider, safe_lang, selected_voice)
    raw_parts = [
        provider,
        safe_lang,
        preview_role,
        selected_voice,
        preview_text,
        _preview_voice_rate(settings, safe_lang, preview_role),
    ]
    if provider == TTS_PROVIDER_VIENEU:
        vieneu_core = normalize_vieneu_core(settings.get("vieneu_core"))
        vieneu_device = _resolve_vieneu_device_for_runtime(settings.get("vieneu_device"))
        vieneu_mode = resolve_vieneu_runtime_mode(settings.get("vieneu_core"), settings.get("vieneu_mode"), vieneu_device)
        vieneu_api_base = str(settings.get("vieneu_api_base") or "")
        vieneu_model_name = resolve_vieneu_model_for_runtime(
            resolve_vieneu_model_name(settings.get("vieneu_model_name"), settings.get("vieneu_mode")),
            vieneu_mode,
            allow_network=False,
        )
        vieneu_backend = resolve_vieneu_runtime_backend(
            vieneu_mode,
            vieneu_model_name,
            vieneu_device,
            settings.get("vieneu_backend"),
        )
        raw_parts.extend([
            vieneu_core,
            vieneu_mode,
            vieneu_api_base,
            vieneu_model_name,
            vieneu_device,
            vieneu_backend,
        ])
    raw_parts.extend([
        str(preview_cfg["temperature"]),
        str(preview_cfg["max_chars_chunk"]),
        str(int(preview_cfg["use_batch"])),
        str(preview_cfg["max_batch_size_run"]),
    ])
    raw = "|".join(raw_parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def preview_tts_sample(*, text: str, settings: dict[str, Any], lang: str = "vi", voice_choice: str = "", provider_override: str | None = None) -> Path:
    preview_text = str(text or "").strip()
    if not preview_text:
        raise ValueError("Preview text is required")

    provider = normalize_tts_provider(provider_override or settings.get("tts_provider"))
    safe_lang = str(lang or "vi").strip().lower()
    selected_voice = str(voice_choice or "").strip()
    preview_cfg = _get_vieneu_preview_config(settings)
    preview_role = _preview_voice_role(provider, safe_lang, selected_voice)
    if not selected_voice:
        narrator_choices = get_voice_choices(tts_provider=provider, lang=safe_lang, role="narrator")
        if narrator_choices:
            selected_voice = narrator_choices[0].value
        preview_role = "narrator"

    preview_limit = int(preview_cfg["text_max_len"])
    if len(preview_text) > preview_limit:
        clipped = preview_text[:preview_limit]
        preview_text = clipped.rsplit(" ", 1)[0].strip() or clipped.strip()

    seg = Segment(
        text=preview_text,
        voice=preview_role,
        rate=_preview_voice_rate(settings, safe_lang, preview_role),
        lang=safe_lang,
        lang_from_tag=True,
    )
    voice_map_vi = {
        "narrator": str(settings.get("voice_narrator") or ""),
        "female": str(settings.get("voice_female") or ""),
        "male": str(settings.get("voice_male") or ""),
    }
    voice_map_en = {
        "narrator": str(settings.get("voice_en_narrator") or ""),
        "female": str(settings.get("voice_en_female") or ""),
        "male": str(settings.get("voice_en_male") or ""),
    }
    if selected_voice:
        target_map = voice_map_en if safe_lang == "en" else voice_map_vi
        for key in ("narrator", "female", "male"):
            target_map[key] = selected_voice

    preview_dir = Path(tempfile.gettempdir()) / "render_audio_gui_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    cache_key = _preview_tts_cache_key(
        provider=provider,
        safe_lang=safe_lang,
        selected_voice=selected_voice,
        preview_text=preview_text,
        settings=settings,
    )
    out_wav = preview_dir / f"preview_{cache_key}.wav"

    if out_wav.exists() and out_wav.stat().st_size > 0:
        return out_wav

    if provider == TTS_PROVIDER_EDGE:
        asyncio.run(tts_segment_to_file(seg, out_wav, voice_map_vi, voice_map_en, abbr_map={}, auto_en_lines=False))
        return out_wav
    if provider == TTS_PROVIDER_VIENEU:
        runtime_mode = resolve_vieneu_runtime_mode(
            settings.get("vieneu_core"),
            settings.get("vieneu_mode"),
            settings.get("vieneu_device"),
        )
        runtime_model_name = resolve_vieneu_model_for_runtime(
            resolve_vieneu_model_name(settings.get("vieneu_model_name"), settings.get("vieneu_mode")),
            runtime_mode,
            allow_network=False,
        )
        runtime_device = _resolve_vieneu_device_for_runtime(settings.get("vieneu_device"))
        runtime_backend = resolve_vieneu_runtime_backend(
            runtime_mode,
            runtime_model_name,
            runtime_device,
            settings.get("vieneu_backend"),
        )
        synthesize_segment_with_vieneu(
            seg,
            out_wav,
            voice_map_vi,
            voice_map_en,
            auto_en_lines=False,
            vieneu_mode=runtime_mode,
            vieneu_api_base=str(settings.get("vieneu_api_base") or ""),
            vieneu_model_name=runtime_model_name,
            vieneu_device=runtime_device,
            backend=runtime_backend,
            vieneu_temperature=float(preview_cfg["temperature"]),
            vieneu_max_chars_chunk=int(preview_cfg["max_chars_chunk"]),
            vieneu_use_batch=bool(preview_cfg["use_batch"]),
            vieneu_max_batch_size_run=int(preview_cfg["max_batch_size_run"]),
        )
        return out_wav
    raise UnsupportedTtsProviderError(f"Unsupported TTS provider: {provider}")


def validate_provider_runtime_settings(settings: dict[str, Any]) -> None:
    provider = normalize_tts_provider(settings.get("tts_provider"))
    if provider != TTS_PROVIDER_VIENEU:
        return

    selected_core = normalize_vieneu_core(settings.get("vieneu_core"))
    selected_mode = normalize_vieneu_mode(settings.get("vieneu_mode"))
    selected_device = _resolve_vieneu_device_for_runtime(settings.get("vieneu_device"))
    runtime_mode = resolve_vieneu_runtime_mode(selected_core, selected_mode, selected_device)
    if runtime_mode == "remote" and not str(settings.get("vieneu_api_base") or "").strip():
        raise ValueError("VieNeu remote API requires an API base")

    model_name = validate_vieneu_mode_model_compatibility(
        selected_mode,
        settings.get("vieneu_model_name"),
    )
    if runtime_mode != "remote":
        resolve_vieneu_model_for_runtime(model_name, runtime_mode, allow_network=False)


def _update_vieneu_voice_catalog_cache(*, core: str, mode: str, api_base: str, model_name: str, voices: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> None:
    try:
        import streamlit as st  # type: ignore
        runtime_cache_key = "|".join((core, mode, api_base, model_name or DEFAULT_VIENEU_MODEL_NAME))
        st.session_state["vieneu_voice_catalog_tested_key"] = runtime_cache_key
        st.session_state["vieneu_voice_catalog_choices"] = list(voices or ())
    except Exception:
        pass


def refresh_vieneu_voices_from_settings(settings: dict[str, Any], *, allow_network: bool = False, force_reload: bool = False) -> str:
    core = normalize_vieneu_core(settings.get("vieneu_core"))
    mode = normalize_vieneu_mode(settings.get("vieneu_mode"))
    device = _resolve_vieneu_device_for_runtime(settings.get("vieneu_device"))
    runtime_mode = resolve_vieneu_runtime_mode(core, mode, device)
    api_base = str(settings.get("vieneu_api_base") or DEFAULT_VIENEU_API_BASE).strip()
    model_name = validate_vieneu_mode_model_compatibility(mode, settings.get("vieneu_model_name"))
    if runtime_mode == "remote" and not api_base:
        raise ValueError("VieNeu remote API requires an API base, for example http://127.0.0.1:23333/v1")

    bootstrap_vieneu_runtime(allow_network=allow_network)
    if force_reload:
        clear_vieneu_runtime_caches()

    bootstrap_vieneu_runtime(allow_network=allow_network)
    if force_reload:
        clear_vieneu_runtime_caches()

    model_name = resolve_vieneu_model_for_runtime(model_name, runtime_mode, allow_network=allow_network)
    voices = list_vieneu_preset_voices(
        mode=runtime_mode,
        api_base=api_base,
        model_name=model_name,
        device=device,
        allow_network=allow_network,
    )
    _update_vieneu_voice_catalog_cache(core=core, mode=mode, api_base=api_base, model_name=model_name, voices=voices)

    if voices:
        preview = ", ".join(label for label, _ in voices[:6])
        suffix = " ..." if len(voices) > 6 else ""
        return f"Refreshed VieNeu voices: {len(voices)} preset(s) ({preview}{suffix})"
    return "Refreshed VieNeu voices but no preset could be loaded yet; the app will fall back to the sample voice list until the runtime model is ready."


def probe_vieneu_core_connection_from_settings(settings: dict[str, Any], *, allow_network: bool = False, force_reload: bool = False) -> str:
    core = normalize_vieneu_core(settings.get("vieneu_core"))
    mode = normalize_vieneu_mode(settings.get("vieneu_mode"))
    device = _resolve_vieneu_device_for_runtime(settings.get("vieneu_device"))
    runtime_mode = resolve_vieneu_runtime_mode(core, mode, device)
    api_base = str(settings.get("vieneu_api_base") or DEFAULT_VIENEU_API_BASE).strip()
    model_name = validate_vieneu_mode_model_compatibility(mode, settings.get("vieneu_model_name"))
    if runtime_mode == "remote" and not api_base:
        raise ValueError("VieNeu remote API requires an API base, for example http://127.0.0.1:23333/v1")

    model_name = resolve_vieneu_model_for_runtime(model_name, runtime_mode, allow_network=allow_network)
    voices = list_vieneu_preset_voices(
        mode=runtime_mode,
        api_base=api_base,
        model_name=model_name,
        device=device,
        allow_network=allow_network,
    )
    _update_vieneu_voice_catalog_cache(core=core, mode=mode, api_base=api_base, model_name=model_name, voices=voices)

    message = [
        f"VieNeu TTS core connection succeeded: mode={mode}",
        f"Model: {model_name or DEFAULT_VIENEU_MODEL_NAME}",
    ]
    if runtime_mode == "remote":
        message.append(f"Remote API base: {api_base}")
        message.append("Fallback when render fails: check that the VieNeu API server is running, the exposed model id is correct, and the /v1 route is reachable.")
    elif mode == "standard":
        message.append("Fallback when render fails: check torch/transformers and the model weights used by standard mode.")
    else:
        message.append("Fallback when render fails: check the vieneu package, llama-cpp-python, onnxruntime, and the turbo-mode GGUF model. The app prefers local/offline cache at startup; use Update model/cache when a fresh download is needed.")
    if voices:
        preview = ", ".join(label for label, _ in voices[:6])
        suffix = " ..." if len(voices) > 6 else ""
        message.append(f"Preset voices: {len(voices)} ({preview}{suffix})")
    else:
        message.append("Could not read preset voices; the app will fall back to the static VieNeu sample voice list.")
    return " | ".join(message)
