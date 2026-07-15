from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from audio.asset_profile_utils import load_asset_profile_manifest
from audio.paths import ASSETS_ROOT, DEFAULT_BGM_DIR, PACKAGE_PROFILE_ROOT
from audio.bgm_config_schema import BgmConfigSchema, load_bgm_config_schema
from audio.profile_manifest_schema import ProfileManifestSchema, load_profile_manifest_schema
from audio.tts_provider import DEFAULT_TTS_PROVIDER, normalize_tts_provider
from audio.adapters.tts_core import get_default_vieneu_local_target, normalize_vieneu_backend, normalize_vieneu_device, resolve_vieneu_model_name
DEFAULT_PROFILE_ROOT = str(PACKAGE_PROFILE_ROOT)
DEFAULT_BGM_DIR_STR = str(DEFAULT_BGM_DIR)
DEFAULT_VOICE_NARRATOR = "Doan"
DEFAULT_VOICE_FEMALE = "Thục Đoan"
DEFAULT_VOICE_MALE = "Vinh"
DEFAULT_EN_VOICE_NARRATOR = "Doan"
DEFAULT_EN_VOICE_FEMALE = "Doan"
DEFAULT_EN_VOICE_MALE = "en-US-GuyNeural"

PROFILE_CONFIG_DEFAULTS: dict[str, Any] = {
    "profile_root": str(DEFAULT_PROFILE_ROOT),
    "asset_profile": "demo",
    "bgm": None,
    "bgmdir": DEFAULT_BGM_DIR_STR,
    "bgm_config": None,
    "abbr_map": str(ASSETS_ROOT / "abbreviation_map.json"),
    "tts_provider": DEFAULT_TTS_PROVIDER,
    "voice_narrator": DEFAULT_VOICE_NARRATOR,
    "voice_female": DEFAULT_VOICE_FEMALE,
    "voice_male": DEFAULT_VOICE_MALE,
    "voice_en_narrator": DEFAULT_EN_VOICE_NARRATOR,
    "voice_en_female": DEFAULT_EN_VOICE_FEMALE,
    "voice_en_male": DEFAULT_EN_VOICE_MALE,
    "voice_narrator_speed": 25,
    "voice_female_speed": 25,
    "voice_male_speed": 25,
    "voice_en_narrator_speed": 25,
    "voice_en_female_speed": 25,
    "voice_en_male_speed": 25,
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

PROFILE_CONFIG_FIELD_NAMES = set(PROFILE_CONFIG_DEFAULTS.keys())

def _normalize_optional_string(value: object) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _normalize_required_string(value: object, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _load_json_dict(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON at {path} must be an object")
    return data


@dataclass(frozen=True)
class ResolvedProfileConfig:
    profile_dir: Optional[Path]
    manifest_path: Optional[Path]
    manifest: dict[str, Any]
    manifest_schema: Optional[ProfileManifestSchema]
    bgm_dir: Path
    bgm_config_path: Optional[Path]
    bgm_schema: Optional[BgmConfigSchema]


@dataclass(frozen=True)
class ProfileConfig:
    profile_root: str
    asset_profile: Optional[str]
    bgm: Optional[str]
    bgmdir: str
    bgm_config: Optional[str]
    abbr_map: str
    tts_provider: str
    voice_narrator: str
    voice_female: str
    voice_male: str
    voice_en_narrator: str
    voice_en_female: str
    voice_en_male: str
    voice_narrator_speed: int = 12
    voice_female_speed: int = 14
    voice_male_speed: int = 10
    voice_en_narrator_speed: int = 12
    voice_en_female_speed: int = 13
    voice_en_male_speed: int = 11
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
        object.__setattr__(self, "profile_root", _normalize_required_string(self.profile_root, "profile_root"))
        object.__setattr__(self, "asset_profile", _normalize_optional_string(self.asset_profile))
        object.__setattr__(self, "bgm", _normalize_optional_string(self.bgm))
        object.__setattr__(self, "bgmdir", _normalize_required_string(self.bgmdir, "bgmdir"))
        object.__setattr__(self, "bgm_config", _normalize_optional_string(self.bgm_config))
        object.__setattr__(self, "abbr_map", _normalize_required_string(self.abbr_map, "abbr_map"))
        object.__setattr__(self, "tts_provider", normalize_tts_provider(self.tts_provider))
        object.__setattr__(self, "voice_narrator", _normalize_required_string(self.voice_narrator, "voice_narrator"))
        object.__setattr__(self, "voice_female", _normalize_required_string(self.voice_female, "voice_female"))
        object.__setattr__(self, "voice_male", _normalize_required_string(self.voice_male, "voice_male"))
        object.__setattr__(self, "voice_en_narrator", _normalize_required_string(self.voice_en_narrator, "voice_en_narrator"))
        object.__setattr__(self, "voice_en_female", _normalize_required_string(self.voice_en_female, "voice_en_female"))
        object.__setattr__(self, "voice_en_male", _normalize_required_string(self.voice_en_male, "voice_en_male"))
        object.__setattr__(self, "voice_narrator_speed", int(self.voice_narrator_speed))
        object.__setattr__(self, "voice_female_speed", int(self.voice_female_speed))
        object.__setattr__(self, "voice_male_speed", int(self.voice_male_speed))
        object.__setattr__(self, "voice_en_narrator_speed", int(self.voice_en_narrator_speed))
        object.__setattr__(self, "voice_en_female_speed", int(self.voice_en_female_speed))
        object.__setattr__(self, "voice_en_male_speed", int(self.voice_en_male_speed))
        object.__setattr__(self, "vieneu_core", str(self.vieneu_core or "local").strip() or "local")
        object.__setattr__(self, "vieneu_mode", str(self.vieneu_mode or "turbo").strip() or "turbo")
        object.__setattr__(self, "vieneu_api_base", str(self.vieneu_api_base or "").strip())
        object.__setattr__(self, "vieneu_model_name", resolve_vieneu_model_name(self.vieneu_model_name, self.vieneu_mode))
        object.__setattr__(self, "vieneu_device", normalize_vieneu_device(self.vieneu_device))
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
        if not self.profile_root.strip():
            raise ValueError("profile_root is required")
        if not self.bgmdir.strip():
            raise ValueError("bgmdir is required")
        if not self.abbr_map.strip():
            raise ValueError("abbr_map is required")

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return dict(PROFILE_CONFIG_DEFAULTS)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ProfileConfig":
        payload = cls.defaults()
        for key, value in raw.items():
            if key in PROFILE_CONFIG_FIELD_NAMES:
                payload[key] = value
        return cls(**payload)

    def to_payload(self) -> dict[str, Any]:
        return {
            "profile_root": self.profile_root,
            "asset_profile": self.asset_profile,
            "bgm": self.bgm,
            "bgmdir": self.bgmdir,
            "bgm_config": self.bgm_config,
            "abbr_map": self.abbr_map,
            "tts_provider": self.tts_provider,
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
        return SimpleNamespace(**self.to_payload())

    def resolve(self) -> ResolvedProfileConfig:
        profile_dir: Optional[Path] = None
        manifest_path: Optional[Path] = None
        manifest: dict[str, Any] = {}
        bgm_config_path: Optional[Path] = None
        bgm_schema: Optional[BgmConfigSchema] = None
        manifest_schema: Optional[ProfileManifestSchema] = None

        if self.asset_profile:
            profile_dir, manifest = load_asset_profile_manifest(self.asset_profile, self.profile_root)
            manifest_path = profile_dir / "manifest.json"
            manifest_schema = load_profile_manifest_schema(manifest_path, expected_profile_id=self.asset_profile)
            bgm_config_path = manifest_schema.resolve_bgm_config_path(profile_dir)
            bgm_dir = manifest_schema.resolve_bgm_dir_path(profile_dir) or (profile_dir / "bgm")
            if bgm_config_path is not None:
                bgm_schema = load_bgm_config_schema(bgm_config_path)
                bgm_dir = bgm_schema.resolve_base_dir(bgm_config_path)
            if not bgm_dir.is_dir():
                raise FileNotFoundError(f"Profile BGM directory does not exist: {bgm_dir}")
        else:
            bgm_dir = Path(self.bgmdir)

        if self.bgm_config and profile_dir is not None:
            explicit = Path(self.bgm_config)
            if not explicit.is_absolute() and not explicit.exists():
                candidate = profile_dir / explicit
                if candidate.exists():
                    bgm_config_path = candidate.resolve()
            elif explicit.exists():
                bgm_config_path = explicit.resolve()
            else:
                bgm_config_path = explicit

        if bgm_config_path is not None and bgm_schema is None and bgm_config_path.is_file():
            bgm_schema = load_bgm_config_schema(bgm_config_path)
            bgm_dir = bgm_schema.resolve_base_dir(bgm_config_path)

        return ResolvedProfileConfig(
            profile_dir=profile_dir,
            manifest_path=manifest_path,
            manifest=manifest,
            manifest_schema=manifest_schema,
            bgm_dir=bgm_dir,
            bgm_config_path=bgm_config_path,
            bgm_schema=bgm_schema,
        )
