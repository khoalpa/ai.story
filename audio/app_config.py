from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from audio.render_audio_app import RenderAudioAppRequest
from audio.adapters.tts_core import get_default_vieneu_local_target, normalize_vieneu_backend, resolve_vieneu_effective_mode, resolve_vieneu_model_name
from audio.tts_provider import DEFAULT_TTS_PROVIDER, normalize_tts_provider
from audio.profile_config import ProfileConfig

APP_CONFIG_ALIASES: dict[str, str] = {
    "debug_mode": "debug",
}

APP_CONFIG_DEFAULTS: dict[str, Any] = {
    "ffmpeg_exe": "ffmpeg",
    "ffprobe_exe": "ffprobe",
    "output_dir": "output",
    "audio_format": "mp3",
    "tts_provider": DEFAULT_TTS_PROVIDER,
    "validate_only": False,
    "debug": False,
    "sentiment_tone": True,
    "auto_en_lines": True,
    "post_fx_preset": "storytelling_vi",
    "max_concurrent_tts": 8,
    "store_path": ".render_audio_gui/jobs.json",
    "runtime_diagnostics": None,
    "vieneu_core": "local",
    "vieneu_mode": "standard",
    "vieneu_api_base": "",
    "vieneu_model_name": get_default_vieneu_local_target("standard"),
    "vieneu_device": "cuda",
    "vieneu_backend": "auto",
    "vieneu_preview_temperature": 0.6,
    "vieneu_preview_max_chars_chunk": 160,
    "vieneu_preview_use_batch": False,
    "vieneu_preview_max_batch_size_run": 1,
    "vieneu_preview_text_max_len": 100,
    "vieneu_render_temperature": 0.7,
    "vieneu_render_max_chars_chunk": 240,
    "vieneu_render_use_batch": False,
    "vieneu_render_max_batch_size_run": 1,
}

APP_CONFIG_FIELD_NAMES = set(APP_CONFIG_DEFAULTS.keys())


def _normalize_required_string(value: object, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _normalize_audio_format(value: object) -> str:
    normalized = str(value or "mp3").strip().lower()
    return normalized if normalized in {"wav", "mp3"} else "mp3"


@dataclass(frozen=True)
class AppConfig:
    ffmpeg_exe: str
    ffprobe_exe: str
    output_dir: Path
    audio_format: str
    tts_provider: str
    validate_only: bool
    debug: bool
    sentiment_tone: bool
    auto_en_lines: bool
    post_fx_preset: str
    max_concurrent_tts: int
    store_path: Path
    runtime_diagnostics: Any = None
    vieneu_core: str = "local"
    vieneu_mode: str = "standard"
    vieneu_api_base: str = ""
    vieneu_model_name: str = get_default_vieneu_local_target("standard")
    vieneu_device: str = "cuda"
    vieneu_backend: str = "auto"
    vieneu_preview_temperature: float = 0.6
    vieneu_preview_max_chars_chunk: int = 160
    vieneu_preview_use_batch: bool = False
    vieneu_preview_max_batch_size_run: int = 1
    vieneu_preview_text_max_len: int = 100
    vieneu_render_temperature: float = 0.7
    vieneu_render_max_chars_chunk: int = 240
    vieneu_render_use_batch: bool = False
    vieneu_render_max_batch_size_run: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "ffmpeg_exe", _normalize_required_string(self.ffmpeg_exe, "ffmpeg_exe"))
        object.__setattr__(self, "ffprobe_exe", _normalize_required_string(self.ffprobe_exe, "ffprobe_exe"))
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "audio_format", _normalize_audio_format(self.audio_format))
        object.__setattr__(self, "tts_provider", normalize_tts_provider(self.tts_provider))
        object.__setattr__(self, "validate_only", bool(self.validate_only))
        object.__setattr__(self, "debug", bool(self.debug))
        object.__setattr__(self, "sentiment_tone", bool(self.sentiment_tone))
        object.__setattr__(self, "auto_en_lines", bool(self.auto_en_lines))
        object.__setattr__(self, "post_fx_preset", _normalize_required_string(self.post_fx_preset, "post_fx_preset"))
        object.__setattr__(self, "max_concurrent_tts", max(1, int(self.max_concurrent_tts)))
        object.__setattr__(self, "store_path", Path(self.store_path))
        object.__setattr__(self, "vieneu_core", str(self.vieneu_core or "local").strip() or "local")
        object.__setattr__(self, "vieneu_mode", resolve_vieneu_effective_mode(self.vieneu_core, self.vieneu_mode, self.vieneu_device))
        object.__setattr__(self, "vieneu_api_base", str(self.vieneu_api_base or "").strip())
        object.__setattr__(self, "vieneu_model_name", resolve_vieneu_model_name(self.vieneu_model_name, self.vieneu_mode))
        object.__setattr__(self, "vieneu_device", str(self.vieneu_device or "cuda").strip().lower() or "cuda")
        object.__setattr__(self, "vieneu_backend", normalize_vieneu_backend(self.vieneu_backend))
        object.__setattr__(self, "vieneu_preview_temperature", float(self.vieneu_preview_temperature if self.vieneu_preview_temperature is not None else 0.6))
        object.__setattr__(self, "vieneu_preview_max_chars_chunk", max(1, int(self.vieneu_preview_max_chars_chunk if self.vieneu_preview_max_chars_chunk is not None else 160)))
        object.__setattr__(self, "vieneu_preview_use_batch", bool(self.vieneu_preview_use_batch))
        object.__setattr__(self, "vieneu_preview_max_batch_size_run", max(1, int(self.vieneu_preview_max_batch_size_run if self.vieneu_preview_max_batch_size_run is not None else 1)))
        object.__setattr__(self, "vieneu_preview_text_max_len", max(1, int(self.vieneu_preview_text_max_len if self.vieneu_preview_text_max_len is not None else 100)))
        object.__setattr__(self, "vieneu_render_temperature", float(self.vieneu_render_temperature if self.vieneu_render_temperature is not None else 0.7))
        object.__setattr__(self, "vieneu_render_max_chars_chunk", max(1, int(self.vieneu_render_max_chars_chunk if self.vieneu_render_max_chars_chunk is not None else 240)))
        object.__setattr__(self, "vieneu_render_use_batch", bool(self.vieneu_render_use_batch))
        object.__setattr__(self, "vieneu_render_max_batch_size_run", max(1, int(self.vieneu_render_max_batch_size_run if self.vieneu_render_max_batch_size_run is not None else 1)))
        self.validate()

    def validate(self) -> None:
        if not str(self.output_dir).strip():
            raise ValueError("output_dir is required")
        if not str(self.store_path).strip():
            raise ValueError("store_path is required")
        if self.audio_format not in {"wav", "mp3"}:
            raise ValueError(f"Unsupported audio_format: {self.audio_format}")
        if not self.tts_provider:
            raise ValueError("tts_provider is required")
        if self.max_concurrent_tts < 1:
            raise ValueError("max_concurrent_tts must be >= 1")

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return dict(APP_CONFIG_DEFAULTS)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AppConfig":
        payload = cls.defaults()
        for key, value in raw.items():
            canonical_key = APP_CONFIG_ALIASES.get(key, key)
            if canonical_key not in APP_CONFIG_FIELD_NAMES:
                continue
            payload[canonical_key] = value
        return cls(**payload)

    def __getitem__(self, key: str):
        return self.to_payload(serialize_paths=True)[key]

    def get(self, key: str, default=None):
        return self.to_payload(serialize_paths=True).get(key, default)

    def to_payload(self, *, serialize_paths: bool = False) -> dict[str, Any]:
        return {
            "ffmpeg_exe": self.ffmpeg_exe,
            "ffprobe_exe": self.ffprobe_exe,
            "output_dir": str(self.output_dir) if serialize_paths else self.output_dir,
            "audio_format": self.audio_format,
            "tts_provider": self.tts_provider,
            "validate_only": self.validate_only,
            "debug_mode": self.debug,
            "debug": self.debug,
            "sentiment_tone": self.sentiment_tone,
            "auto_en_lines": self.auto_en_lines,
            "post_fx_preset": self.post_fx_preset,
            "max_concurrent_tts": self.max_concurrent_tts,
            "store_path": str(self.store_path) if serialize_paths else self.store_path,
            "runtime_diagnostics": self.runtime_diagnostics,
            "vieneu_core": self.vieneu_core,
            "vieneu_mode": self.vieneu_mode,
            "vieneu_api_base": self.vieneu_api_base,
            "vieneu_model_name": self.vieneu_model_name,
            "vieneu_device": self.vieneu_device,
            "vieneu_backend": self.vieneu_backend,
            "vieneu_preview_temperature": self.vieneu_preview_temperature,
            "vieneu_preview_max_chars_chunk": self.vieneu_preview_max_chars_chunk,
            "vieneu_preview_use_batch": self.vieneu_preview_use_batch,
            "vieneu_preview_max_batch_size_run": self.vieneu_preview_max_batch_size_run,
            "vieneu_preview_text_max_len": self.vieneu_preview_text_max_len,
            "vieneu_render_temperature": self.vieneu_render_temperature,
            "vieneu_render_max_chars_chunk": self.vieneu_render_max_chars_chunk,
            "vieneu_render_use_batch": self.vieneu_render_use_batch,
            "vieneu_render_max_batch_size_run": self.vieneu_render_max_batch_size_run,
        }

    def to_namespace(self) -> SimpleNamespace:
        return SimpleNamespace(**self.to_payload(serialize_paths=True))

    def to_request_mapping(self, input_path: Path, profile_config: ProfileConfig) -> dict[str, Any]:
        payload = profile_config.to_payload()
        payload.update({
            "input_path": input_path,
            "output_dir": self.output_dir,
            "audio_format": self.audio_format,
            "tts_provider": self.tts_provider,
            "validate_only": self.validate_only,
            "debug": self.debug,
            "sentiment_tone": self.sentiment_tone,
            "auto_en_lines": self.auto_en_lines,
            "post_fx_preset": self.post_fx_preset,
            "max_concurrent_tts": self.max_concurrent_tts,
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
        })
        return payload

    def to_request(self, input_path: Path, profile_config: ProfileConfig) -> RenderAudioAppRequest:
        return RenderAudioAppRequest.from_mapping(self.to_request_mapping(input_path, profile_config))
