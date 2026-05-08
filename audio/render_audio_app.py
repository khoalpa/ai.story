from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from audio.adapters.edge_tts import load_abbreviation_map
from audio.adapters.tts_core import (
    get_default_vieneu_local_target,
    resolve_vieneu_effective_mode,
    resolve_vieneu_model_for_runtime,
    resolve_vieneu_model_name,
    resolve_vieneu_runtime_backend,
    warmup_vieneu_engine,
)
from audio.logging_utils import get_logger
from audio.render_job import RenderJobArtifacts, RenderJobPaths, RuntimeContext, VoiceRuntimeMaps
from audio.paths import ASSETS_ROOT, PACKAGE_PROFILE_ROOT
from audio.render_events import (
    AppDebugSavedEvent,
    AppPathsResolvedEvent,
    AppPhaseCompletedEvent,
    AppPhaseStartedEvent,
    AppPreviewReadyEvent,
    AppRenderCompletedEvent,
    AppResourcesLoadedEvent,
    AppRuntimeResolvedEvent,
    AppValidationCompletedEvent,
    RenderEventSink,
    emit_render_event,
)
from audio.runtime_checks import (
    collect_runtime_diagnostics,
    runtime_diagnostics_to_lines,
    validate_runtime_executables,
)
from audio.services.render_orchestration import run_render_job
from audio.services.render_runtime import (
    build_voice_maps,
    build_voice_rate_map,
    resolve_asset_profile_runtime,
    resolve_job_paths,
    resolve_profile_relative_path,
    resolve_runtime_context,
)
from audio.services.render_script import (
    load_text_file,
    parse_script_to_segments,
    prepare_segments,
    save_segments_debug_json,
)
from audio.tts_provider import DEFAULT_TTS_PROVIDER, TTS_PROVIDER_VIENEU, normalize_tts_provider
from audio.validate_plain_script import load_text_file as load_validation_lines
from audio.validate_plain_script import validate_script

logger = get_logger(__name__)

REQUEST_ALIASES: dict[str, str] = {
    "input": "input_path",
    "output": "output_dir",
    "debug_mode": "debug",
}

REQUEST_DEFAULTS: dict[str, Any] = {
    "asset_profile": None,
    "profile_root": str(PACKAGE_PROFILE_ROOT),
    "bgm": None,
    "bgmdir": "audio/bgm",
    "voice_narrator": "vi-VN-NamMinhNeural",
    "voice_female": "vi-VN-HoaiMyNeural",
    "voice_male": "vi-VN-NamMinhNeural",
    "voice_en_narrator": "en-US-AndrewNeural",
    "voice_en_female": "en-US-AvaNeural",
    "voice_en_male": "en-US-AndrewNeural",
    "voice_narrator_speed": 12,
    "voice_female_speed": 14,
    "voice_male_speed": 10,
    "voice_en_narrator_speed": 12,
    "voice_en_female_speed": 13,
    "voice_en_male_speed": 11,
    "abbr_map": str(ASSETS_ROOT / "abbreviation_map.json"),
    "bgm_config": None,
    "sentiment_tone": False,
    "validate_only": False,
    "debug": False,
    "auto_en_lines": False,
    "post_fx_preset": "none",
    "max_concurrent_tts": 8,
    "tts_provider": DEFAULT_TTS_PROVIDER,
    "audio_format": "mp3",
    "vieneu_core": "local",
    "vieneu_mode": "standard",
    "vieneu_api_base": "",
    "vieneu_model_name": get_default_vieneu_local_target("standard"),
    "vieneu_device": "cuda",
    "vieneu_backend": "auto",
    "vieneu_render_temperature": 0.7,
    "vieneu_render_max_chars_chunk": 240,
    "vieneu_render_use_batch": False,
    "vieneu_render_max_batch_size_run": 1,
}

REQUEST_FIELD_NAMES = {
    "input_path",
    "output_dir",
    *REQUEST_DEFAULTS.keys(),
}


def _normalize_audio_format(value: object) -> str:
    normalized = str(value or REQUEST_DEFAULTS["audio_format"]).strip().lower()
    return normalized if normalized in {"wav", "mp3"} else REQUEST_DEFAULTS["audio_format"]


def _normalize_vieneu_core(value: object) -> str:
    normalized = str(value or "local").strip().lower().replace("-", "_").replace(" ", "_")
    return "remote_api" if normalized in {"remote", "remote_api", "api", "remoteapi"} else "local"


@dataclass(frozen=True)
class RenderAudioAppRequest:
    input_path: Path
    output_dir: Path
    asset_profile: Optional[str]
    profile_root: str
    bgm: Optional[str]
    bgmdir: str
    voice_narrator: str
    voice_female: str
    voice_male: str
    voice_en_narrator: str
    voice_en_female: str
    voice_en_male: str
    abbr_map: str
    bgm_config: Optional[str]
    sentiment_tone: bool
    validate_only: bool
    debug: bool
    auto_en_lines: bool
    post_fx_preset: str
    max_concurrent_tts: int
    voice_narrator_speed: int = 12
    voice_female_speed: int = 14
    voice_male_speed: int = 10
    voice_en_narrator_speed: int = 12
    voice_en_female_speed: int = 13
    voice_en_male_speed: int = 11
    tts_provider: str = DEFAULT_TTS_PROVIDER
    audio_format: str = "mp3"
    vieneu_core: str = "local"
    vieneu_mode: str = "standard"
    vieneu_api_base: str = ""
    vieneu_model_name: str = get_default_vieneu_local_target("standard")
    vieneu_device: str = "cuda"
    vieneu_backend: str = "auto"
    vieneu_render_temperature: float = 0.7
    vieneu_render_max_chars_chunk: int = 240
    vieneu_render_use_batch: bool = False
    vieneu_render_max_batch_size_run: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_path", Path(self.input_path))
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "asset_profile", self._normalize_optional_string(self.asset_profile))
        object.__setattr__(self, "profile_root", self._normalize_required_string(self.profile_root, "profile_root"))
        object.__setattr__(self, "bgm", self._normalize_optional_string(self.bgm))
        object.__setattr__(self, "bgmdir", self._normalize_required_string(self.bgmdir, "bgmdir"))
        object.__setattr__(self, "voice_narrator", self._normalize_required_string(self.voice_narrator, "voice_narrator"))
        object.__setattr__(self, "voice_female", self._normalize_required_string(self.voice_female, "voice_female"))
        object.__setattr__(self, "voice_male", self._normalize_required_string(self.voice_male, "voice_male"))
        object.__setattr__(self, "voice_en_narrator", self._normalize_required_string(self.voice_en_narrator, "voice_en_narrator"))
        object.__setattr__(self, "voice_en_female", self._normalize_required_string(self.voice_en_female, "voice_en_female"))
        object.__setattr__(self, "voice_en_male", self._normalize_required_string(self.voice_en_male, "voice_en_male"))
        object.__setattr__(self, "voice_narrator_speed", int(self.voice_narrator_speed))
        object.__setattr__(self, "voice_female_speed", int(self.voice_female_speed))
        object.__setattr__(self, "voice_male_speed", int(self.voice_male_speed))
        object.__setattr__(self, "voice_en_narrator_speed", int(self.voice_en_narrator_speed))
        object.__setattr__(self, "voice_en_female_speed", int(self.voice_en_female_speed))
        object.__setattr__(self, "voice_en_male_speed", int(self.voice_en_male_speed))
        object.__setattr__(self, "abbr_map", self._normalize_required_string(self.abbr_map, "abbr_map"))
        object.__setattr__(self, "bgm_config", self._normalize_optional_string(self.bgm_config))
        object.__setattr__(self, "sentiment_tone", bool(self.sentiment_tone))
        object.__setattr__(self, "validate_only", bool(self.validate_only))
        object.__setattr__(self, "debug", bool(self.debug))
        object.__setattr__(self, "auto_en_lines", bool(self.auto_en_lines))
        object.__setattr__(self, "post_fx_preset", self._normalize_required_string(self.post_fx_preset, "post_fx_preset"))
        object.__setattr__(self, "max_concurrent_tts", max(1, int(self.max_concurrent_tts)))
        object.__setattr__(self, "tts_provider", normalize_tts_provider(self.tts_provider))
        object.__setattr__(self, "audio_format", _normalize_audio_format(self.audio_format))
        normalized_vieneu_core = _normalize_vieneu_core(self.vieneu_core)
        normalized_vieneu_mode = resolve_vieneu_effective_mode(normalized_vieneu_core, self.vieneu_mode, self.vieneu_device)
        normalized_vieneu_device = str(self.vieneu_device or "cuda").strip().lower() or "cuda"
        object.__setattr__(self, "vieneu_core", normalized_vieneu_core)
        object.__setattr__(self, "vieneu_mode", normalized_vieneu_mode)
        object.__setattr__(self, "vieneu_api_base", str(self.vieneu_api_base or "").strip())
        object.__setattr__(self, "vieneu_model_name", resolve_vieneu_model_name(self.vieneu_model_name, self.vieneu_mode))
        object.__setattr__(self, "vieneu_device", normalized_vieneu_device)
        object.__setattr__(self, "vieneu_backend", str(self.vieneu_backend or "auto").strip().lower() or "auto")
        object.__setattr__(
            self,
            "vieneu_render_temperature",
            float(self.vieneu_render_temperature if self.vieneu_render_temperature is not None else 0.7),
        )
        object.__setattr__(
            self,
            "vieneu_render_max_chars_chunk",
            max(1, int(self.vieneu_render_max_chars_chunk if self.vieneu_render_max_chars_chunk is not None else 240)),
        )
        object.__setattr__(self, "vieneu_render_use_batch", bool(self.vieneu_render_use_batch))
        object.__setattr__(
            self,
            "vieneu_render_max_batch_size_run",
            max(1, int(self.vieneu_render_max_batch_size_run if self.vieneu_render_max_batch_size_run is not None else 1)),
        )
        self.validate()

    @staticmethod
    def _normalize_optional_string(value: object) -> Optional[str]:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _normalize_required_string(value: object, field_name: str) -> str:
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError(f"{field_name} is required")
        return text

    def validate(self) -> None:
        if not str(self.input_path).strip():
            raise ValueError("input_path is required")
        if not str(self.output_dir).strip():
            raise ValueError("output_dir is required")
        if self.audio_format not in {"wav", "mp3"}:
            raise ValueError(f"Unsupported audio_format: {self.audio_format}")
        if self.max_concurrent_tts < 1:
            raise ValueError("max_concurrent_tts must be >= 1")

    def to_payload(self, *, serialize_paths: bool = False) -> dict[str, Any]:
        return {
            "input_path": str(self.input_path) if serialize_paths else self.input_path,
            "output_dir": str(self.output_dir) if serialize_paths else self.output_dir,
            "asset_profile": self.asset_profile,
            "profile_root": self.profile_root,
            "bgm": self.bgm,
            "bgmdir": self.bgmdir,
            "voice_narrator": self.voice_narrator,
            "voice_female": self.voice_female,
            "voice_male": self.voice_male,
            "voice_en_narrator": self.voice_en_narrator,
            "voice_en_female": self.voice_en_female,
            "voice_en_male": self.voice_en_male,
            "voice_narrator_speed": self.voice_narrator_speed,
            "voice_female_speed": self.voice_female_speed,
            "voice_male_speed": self.voice_male_speed,
            "voice_en_narrator_speed": self.voice_en_narrator_speed,
            "voice_en_female_speed": self.voice_en_female_speed,
            "voice_en_male_speed": self.voice_en_male_speed,
            "abbr_map": self.abbr_map,
            "bgm_config": self.bgm_config,
            "sentiment_tone": self.sentiment_tone,
            "validate_only": self.validate_only,
            "debug": self.debug,
            "auto_en_lines": self.auto_en_lines,
            "post_fx_preset": self.post_fx_preset,
            "max_concurrent_tts": self.max_concurrent_tts,
            "tts_provider": self.tts_provider,
            "audio_format": self.audio_format,
            "vieneu_core": self.vieneu_core,
            "vieneu_mode": self.vieneu_mode,
            "vieneu_api_base": self.vieneu_api_base,
            "vieneu_model_name": self.vieneu_model_name,
            "vieneu_device": self.vieneu_device,
            "vieneu_backend": self.vieneu_backend,
            "vieneu_render_temperature": self.vieneu_render_temperature,
            "vieneu_render_max_chars_chunk": self.vieneu_render_max_chars_chunk,
            "vieneu_render_use_batch": self.vieneu_render_use_batch,
            "vieneu_render_max_batch_size_run": self.vieneu_render_max_batch_size_run,
        }

    def to_namespace(self) -> SimpleNamespace:
        payload = self.to_payload(serialize_paths=True)
        payload["input"] = payload["input_path"]
        payload["output"] = payload["output_dir"]
        return SimpleNamespace(**payload)

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return dict(REQUEST_DEFAULTS)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RenderAudioAppRequest":
        payload = cls.defaults()
        for key, value in raw.items():
            canonical_key = REQUEST_ALIASES.get(key, key)
            if canonical_key not in REQUEST_FIELD_NAMES:
                continue
            payload[canonical_key] = value
        if payload.get("input_path") is None:
            raise ValueError("input_path is required")
        if payload.get("output_dir") is None:
            raise ValueError("output_dir is required")
        return cls(**payload)


@dataclass(frozen=True)
class RenderAudioAppResult:
    request: RenderAudioAppRequest
    mode: str
    runtime_ctx: RuntimeContext
    voice_maps: VoiceRuntimeMaps
    job_paths: RenderJobPaths
    abbr_map_path: Path
    abbr_map: dict[str, str]
    preview: Optional[RenderJobArtifacts] = None
    render_artifacts: Optional[RenderJobArtifacts] = None
    validate_exit_code: Optional[int] = None
    validate_errors: tuple[str, ...] = ()
    validate_warnings_count: int = 0
    cli_bgm_config: Optional[Path] = None
    profile_bgm_config: Optional[Path] = None


def create_app_request_from_args(args) -> RenderAudioAppRequest:
    raw = vars(args) if hasattr(args, "__dict__") else dict(args)
    return RenderAudioAppRequest.from_mapping(raw)


def create_default_app_request(input_path: Path, output_dir: Path) -> RenderAudioAppRequest:
    return RenderAudioAppRequest.from_mapping({"input_path": input_path, "output_dir": output_dir})


def validate_only_script(input_path: Path) -> tuple[int, tuple[str, ...], int]:
    result = validate_script(load_validation_lines(input_path))
    if result.ok:
        return 0, (), len(result.warnings)
    errors = tuple(f"line {issue.line_no}: {issue.message}" for issue in result.errors)
    return 1, errors, len(result.warnings)


def _to_namespace(request: RenderAudioAppRequest) -> SimpleNamespace:
    return request.to_namespace()


def _resolve_job_paths_compat(input_path: Path, output_dir: Path, audio_format: str) -> RenderJobPaths:
    try:
        sig = inspect.signature(resolve_job_paths)
        if "audio_format" in sig.parameters:
            return resolve_job_paths(input_path, output_dir, audio_format=audio_format)
    except (TypeError, ValueError):
        pass
    return resolve_job_paths(input_path, output_dir)


def _run_render_job_compat(
    *,
    segments,
    paths,
    runtime_ctx,
    voice_maps,
    voice_rate_map,
    abbr_map,
    auto_en_lines: bool,
    max_concurrent_tts: int,
    tts_provider: str,
    post_fx_preset: str,
    ffmpeg_exe: str,
    ffprobe_exe: str,
    event_sink: RenderEventSink | None,
    audio_format: str,
    vieneu_core: str = "local",
    vieneu_mode: str = "standard",
    vieneu_api_base: str = "",
    vieneu_model_name: str = get_default_vieneu_local_target("standard"),
    vieneu_device: str = "cuda",
    vieneu_backend: str = "auto",
    vieneu_render_temperature: float = 0.7,
    vieneu_render_max_chars_chunk: int = 240,
    vieneu_render_use_batch: bool = False,
    vieneu_render_max_batch_size_run: int = 1,
):
    base_kwargs = {
        "segments": segments,
        "paths": paths,
        "runtime_ctx": runtime_ctx,
        "voice_maps": voice_maps,
        "voice_rate_map": voice_rate_map,
        "abbr_map": abbr_map,
        "auto_en_lines": auto_en_lines,
        "max_concurrent_tts": max_concurrent_tts,
        "tts_provider": tts_provider,
        "post_fx_preset": post_fx_preset,
        "ffmpeg_exe": ffmpeg_exe,
        "ffprobe_exe": ffprobe_exe,
        "event_sink": event_sink,
        "audio_format": audio_format,
        "vieneu_core": vieneu_core,
        "vieneu_mode": vieneu_mode,
        "vieneu_api_base": vieneu_api_base,
        "vieneu_model_name": vieneu_model_name,
        "vieneu_device": vieneu_device,
        "vieneu_backend": vieneu_backend,
        "vieneu_render_temperature": vieneu_render_temperature,
        "vieneu_render_max_chars_chunk": vieneu_render_max_chars_chunk,
        "vieneu_render_use_batch": vieneu_render_use_batch,
        "vieneu_render_max_batch_size_run": vieneu_render_max_batch_size_run,
    }
    try:
        sig = inspect.signature(run_render_job)
        filtered_kwargs = {name: value for name, value in base_kwargs.items() if name in sig.parameters}
        return run_render_job(**filtered_kwargs)
    except (TypeError, ValueError):
        pass
    return run_render_job(**base_kwargs)


def run_render_audio_app(
    request: RenderAudioAppRequest,
    *,
    ffmpeg_exe: str,
    ffprobe_exe: str,
    event_sink: RenderEventSink | None = None,
) -> RenderAudioAppResult:
    if not request.input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {request.input_path}")

    request.output_dir.mkdir(parents=True, exist_ok=True)
    emit_render_event(
        event_sink,
        AppPathsResolvedEvent(input_path=request.input_path, output_dir=request.output_dir),
    )
    args = _to_namespace(request)

    runtime_ctx = resolve_runtime_context(args)
    voice_maps = build_voice_maps(args, runtime_ctx.profile_voice_defaults)
    voice_rate_map = build_voice_rate_map(args)
    job_paths = _resolve_job_paths_compat(request.input_path, request.output_dir, request.audio_format)
    logger.info("Render output directory resolved: %s", request.output_dir)
    logger.info(
        "Render targets | audio: %s | subtitle: %s | wav_dir: %s | debug_json: %s",
        job_paths.out_file,
        job_paths.srt_path,
        job_paths.wav_dir,
        job_paths.debug_json,
    )
    emit_render_event(
        event_sink,
        AppRuntimeResolvedEvent(
            request=request,
            runtime_ctx=runtime_ctx,
            voice_maps=voice_maps,
            voice_rate_map=voice_rate_map,
            job_paths=job_paths,
        ),
    )

    abbr_map_path = resolve_profile_relative_path(runtime_ctx.profile_dir, request.abbr_map)
    abbr_map = load_abbreviation_map(abbr_map_path)

    cli_bgm_config = (
        resolve_profile_relative_path(runtime_ctx.profile_dir, request.bgm_config)
        if request.bgm_config
        else None
    )
    profile_bgm_config = None
    if request.asset_profile and not request.bgm_config:
        _, _, raw_profile_bgm_config, _ = resolve_asset_profile_runtime(args)
        if raw_profile_bgm_config:
            profile_bgm_config = Path(raw_profile_bgm_config)

    emit_render_event(
        event_sink,
        AppResourcesLoadedEvent(
            abbr_map_path=abbr_map_path,
            abbr_map=abbr_map,
            cli_bgm_config=cli_bgm_config,
            profile_bgm_config=profile_bgm_config,
        ),
    )

    if request.validate_only:
        exit_code, validate_errors, warnings_count = validate_only_script(request.input_path)
        emit_render_event(
            event_sink,
            AppValidationCompletedEvent(
                input_path=request.input_path,
                exit_code=exit_code,
                errors=validate_errors,
                warnings_count=warnings_count,
            ),
        )
        return RenderAudioAppResult(
            request=request,
            mode="validate_only",
            runtime_ctx=runtime_ctx,
            voice_maps=voice_maps,
            job_paths=job_paths,
            abbr_map_path=abbr_map_path,
            abbr_map=abbr_map,
            validate_exit_code=exit_code,
            validate_errors=validate_errors,
            validate_warnings_count=warnings_count,
            cli_bgm_config=cli_bgm_config,
            profile_bgm_config=profile_bgm_config,
        )

    emit_render_event(
        event_sink,
        AppPhaseStartedEvent(phase="parse", details={"input_path": request.input_path}),
    )
    full_text = load_text_file(request.input_path)
    parse_script_to_segments(full_text, voice_rate_map=voice_rate_map)
    emit_render_event(
        event_sink,
        AppPhaseCompletedEvent(phase="parse", details={"input_path": request.input_path}),
    )

    emit_render_event(
        event_sink,
        AppPhaseStartedEvent(phase="prepare", details={"output_dir": request.output_dir}),
    )
    preview = prepare_segments(
        full_text,
        bgm_fallback=request.bgm,
        runtime_ctx=runtime_ctx,
        sentiment_tone=request.sentiment_tone,
        voice_rate_map=voice_rate_map,
    )
    emit_render_event(
        event_sink,
        AppPreviewReadyEvent(preview=preview, sentiment_tone=request.sentiment_tone),
    )
    emit_render_event(
        event_sink,
        AppPhaseCompletedEvent(phase="prepare", details={"output_dir": request.output_dir}),
    )

    if request.debug:
        save_segments_debug_json(preview.segments, job_paths.debug_json)
        preview = RenderJobArtifacts(
            segments=preview.segments,
            estimated_duration_seconds=preview.estimated_duration_seconds,
            estimated_duration_hms=preview.estimated_duration_hms,
            debug_json=job_paths.debug_json,
        )
        emit_render_event(event_sink, AppDebugSavedEvent(debug_json=job_paths.debug_json))
        return RenderAudioAppResult(
            request=request,
            mode="debug",
            runtime_ctx=runtime_ctx,
            voice_maps=voice_maps,
            voice_rate_map=voice_rate_map,
            job_paths=job_paths,
            abbr_map_path=abbr_map_path,
            abbr_map=abbr_map,
            preview=preview,
            cli_bgm_config=cli_bgm_config,
            profile_bgm_config=profile_bgm_config,
        )

    runtime_bins = validate_runtime_executables(ffmpeg_exe, ffprobe_exe)
    diagnostics = collect_runtime_diagnostics(runtime_bins.ffmpeg_exe, runtime_bins.ffprobe_exe)
    logger.info(
        "Resolved runtime dependencies | %s",
        " | ".join(runtime_diagnostics_to_lines(diagnostics)),
    )

    if normalize_tts_provider(request.tts_provider) == TTS_PROVIDER_VIENEU:
        resolved_runtime_model = resolve_vieneu_model_for_runtime(
            request.vieneu_model_name,
            request.vieneu_mode,
            allow_network=False,
        )
        resolved_runtime_backend = resolve_vieneu_runtime_backend(
            request.vieneu_mode,
            resolved_runtime_model,
            request.vieneu_device,
            request.vieneu_backend,
        )
        logger.info(
            "Prewarming VieNeu runtime | mode=%s | model=%s | device=%s | backend=%s",
            request.vieneu_mode,
            request.vieneu_model_name,
            request.vieneu_device,
            request.vieneu_backend,
        )
        logger.info(
            "VieNeu runtime resolved | mode=%s | resolved runtime model=%s | device=%s | backend=%s",
            request.vieneu_mode,
            resolved_runtime_model,
            request.vieneu_device,
            resolved_runtime_backend,
        )
        warmup_vieneu_engine(
            mode=request.vieneu_mode,
            api_base=request.vieneu_api_base,
            model_name=request.vieneu_model_name,
            device=request.vieneu_device,
            backend=request.vieneu_backend,
            allow_network=False,
        )

    render_artifacts = _run_render_job_compat(
        segments=preview.segments,
        paths=job_paths,
        runtime_ctx=runtime_ctx,
        voice_maps=voice_maps,
        voice_rate_map=voice_rate_map,
        abbr_map=abbr_map,
        auto_en_lines=request.auto_en_lines,
        max_concurrent_tts=request.max_concurrent_tts,
        tts_provider=request.tts_provider,
        post_fx_preset=request.post_fx_preset,
        ffmpeg_exe=ffmpeg_exe,
        ffprobe_exe=ffprobe_exe,
        event_sink=event_sink,
        audio_format=request.audio_format,
        vieneu_core=request.vieneu_core,
        vieneu_mode=request.vieneu_mode,
        vieneu_api_base=request.vieneu_api_base,
        vieneu_model_name=request.vieneu_model_name,
        vieneu_device=request.vieneu_device,
        vieneu_backend=request.vieneu_backend,
        vieneu_render_temperature=request.vieneu_render_temperature,
        vieneu_render_max_chars_chunk=request.vieneu_render_max_chars_chunk,
        vieneu_render_use_batch=request.vieneu_render_use_batch,
        vieneu_render_max_batch_size_run=request.vieneu_render_max_batch_size_run,
    )
    emit_render_event(event_sink, AppRenderCompletedEvent(render_artifacts=render_artifacts))
    return RenderAudioAppResult(
        request=request,
        mode="render",
        runtime_ctx=runtime_ctx,
        voice_maps=voice_maps,
        job_paths=job_paths,
        abbr_map_path=abbr_map_path,
        abbr_map=abbr_map,
        preview=preview,
        render_artifacts=render_artifacts,
        cli_bgm_config=cli_bgm_config,
        profile_bgm_config=profile_bgm_config,
    )
