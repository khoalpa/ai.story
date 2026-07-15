from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from audio.asset_profile_utils import resolve_asset_profile_contract
from audio.bgm_config_utils import BgmRuntimeConfig, load_bgm_runtime_config
from audio.paths import PACKAGE_PROFILE_ROOT
from audio.profile_config import ProfileConfig
from audio.render_job import RenderJobPaths, RuntimeContext, VoiceRuntimeMaps
from audio.tts_provider import TTS_PROVIDER_VIENEU, normalize_tts_provider
from audio.adapters.tts_core import list_vieneu_preset_voices, migrate_vieneu_legacy_voice_id, normalize_vieneu_mode, resolve_vieneu_model_name
from audio.pipeline.flow_state import DEFAULT_VOICE_RATE_MAP, normalize_rate_value

DEFAULT_VOICE_NARRATOR = "vi-VN-HoaiMyNeural"
DEFAULT_VOICE_FEMALE = "vi-VN-HoaiMyNeural"
DEFAULT_VOICE_MALE = "vi-VN-NamMinhNeural"

DEFAULT_EN_VOICE_NARRATOR = "Doan"
DEFAULT_EN_VOICE_FEMALE = "Doan"
DEFAULT_EN_VOICE_MALE = "en-US-GuyNeural"

DEFAULT_PROFILE_ROOT = PACKAGE_PROFILE_ROOT


def resolve_job_paths(input_path: Path, output_dir: Path, audio_format: str = "wav") -> RenderJobPaths:
    return RenderJobPaths(
        out_dir=output_dir,
        wav_dir=output_dir / f"{input_path.stem}_wav",
        out_file=output_dir / f"{input_path.stem}.{audio_format.lower()}",
        srt_path=output_dir / f"{input_path.stem}.srt",
        debug_json=output_dir / f"{input_path.stem}_segments_debug.json",
    )


def resolve_profile_relative_path(profile_dir: Optional[Path], raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute() or path.exists() or profile_dir is None:
        return path
    return profile_dir / path


def resolve_asset_profile_runtime(args) -> Tuple[Optional[Path], Dict[str, str], Optional[str], Optional[str]]:
    raw = vars(args) if hasattr(args, "__dict__") else dict(args)
    profile_config = ProfileConfig.from_mapping(raw)
    if profile_config.asset_profile:
        contract = resolve_asset_profile_contract(profile_config.asset_profile, profile_config.profile_root)
        return (
            contract.profile_dir,
            dict(contract.voice_defaults or {}),
            str(contract.bgm_config) if contract.bgm_config and contract.bgm_config.is_file() else None,
            str(contract.bgm_dir) if contract.bgm_dir else None,
        )

    resolved = profile_config.resolve()
    voice_defaults = dict(resolved.manifest_schema.voices) if resolved.manifest_schema is not None else {}
    return (
        resolved.profile_dir,
        voice_defaults,
        str(resolved.bgm_config_path) if resolved.bgm_config_path and resolved.bgm_config_path.is_file() else None,
        str(resolved.bgm_dir) if resolved.bgm_dir else None,
    )


def resolve_runtime_context(args) -> RuntimeContext:
    profile_dir, profile_voice_defaults, profile_bgm_config, profile_bgmdir = resolve_asset_profile_runtime(args)

    bgmdir_value = profile_bgmdir or args.bgmdir
    bgm_dir = resolve_profile_relative_path(profile_dir, bgmdir_value)
    bgm_dir.mkdir(parents=True, exist_ok=True)

    config_path = profile_bgm_config or args.bgm_config
    if config_path and profile_dir is not None:
        maybe_profile_path = profile_dir / config_path
        if not Path(config_path).exists() and maybe_profile_path.exists():
            config_path = str(maybe_profile_path)

    runtime_config = load_bgm_runtime_config(config_path) or BgmRuntimeConfig()
    return RuntimeContext(
        profile_dir=profile_dir,
        profile_voice_defaults=profile_voice_defaults,
        runtime_config=runtime_config,
        bgm_dir=bgm_dir,
    )


def _resolve_voice_runtime_value(gui_value: object, profile_voice_defaults: Dict[str, str], *profile_keys: str) -> str:
    selected = str(gui_value or "").strip()
    if selected:
        return selected
    for key in profile_keys:
        candidate = str(profile_voice_defaults.get(key) or "").strip()
        if candidate:
            return candidate
    return ""


def _coerce_vieneu_voice_runtime_value(args, selected: object) -> str:
    raw = str(selected or "").strip()
    if not raw:
        return ""
    try:
        available = tuple(
            list_vieneu_preset_voices(
                mode=normalize_vieneu_mode(getattr(args, "vieneu_mode", "turbo")),
                api_base=str(getattr(args, "vieneu_api_base", "") or ""),
                model_name=resolve_vieneu_model_name(getattr(args, "vieneu_model_name", ""), getattr(args, "vieneu_mode", "turbo")),
                allow_network=False,
            )
        )
        migrated = str(migrate_vieneu_legacy_voice_id(raw, available)).strip()
        return migrated or raw
    except Exception:
        return raw


def _resolve_voice_rate_value(raw_value: object, *, lang: str, voice: str) -> str:
    key = f"{lang}_{voice}"
    fallback = DEFAULT_VOICE_RATE_MAP.get(key, "0%")
    return normalize_rate_value(raw_value, fallback=fallback)


def build_voice_rate_map(args) -> Dict[str, str]:
    return {
        "vi_narrator": _resolve_voice_rate_value(getattr(args, "voice_narrator_speed", 25), lang="vi", voice="narrator"),
        "vi_female": _resolve_voice_rate_value(getattr(args, "voice_female_speed", 25), lang="vi", voice="female"),
        "vi_male": _resolve_voice_rate_value(getattr(args, "voice_male_speed", 25), lang="vi", voice="male"),
        "en_narrator": _resolve_voice_rate_value(getattr(args, "voice_en_narrator_speed", 25), lang="en", voice="narrator"),
        "en_female": _resolve_voice_rate_value(getattr(args, "voice_en_female_speed", 25), lang="en", voice="female"),
        "en_male": _resolve_voice_rate_value(getattr(args, "voice_en_male_speed", 25), lang="en", voice="male"),
    }


def build_voice_maps(args, profile_voice_defaults: Dict[str, str]) -> VoiceRuntimeMaps:
    voice_narrator = _resolve_voice_runtime_value(
        getattr(args, "voice_narrator", ""),
        profile_voice_defaults,
        "vi_narrator",
        "voice_narrator",
    )
    voice_female = _resolve_voice_runtime_value(
        getattr(args, "voice_female", ""),
        profile_voice_defaults,
        "vi_female",
        "voice_female",
    )
    voice_male = _resolve_voice_runtime_value(
        getattr(args, "voice_male", ""),
        profile_voice_defaults,
        "vi_male",
        "voice_male",
    )
    voice_en_narrator = _resolve_voice_runtime_value(
        getattr(args, "voice_en_narrator", ""),
        profile_voice_defaults,
        "en_narrator",
        "voice_en_narrator",
    )
    voice_en_female = _resolve_voice_runtime_value(
        getattr(args, "voice_en_female", ""),
        profile_voice_defaults,
        "en_female",
        "voice_en_female",
    )
    voice_en_male = _resolve_voice_runtime_value(
        getattr(args, "voice_en_male", ""),
        profile_voice_defaults,
        "en_male",
        "voice_en_male",
    )

    provider = normalize_tts_provider(getattr(args, "tts_provider", ""))
    if provider == TTS_PROVIDER_VIENEU:
        voice_narrator = _coerce_vieneu_voice_runtime_value(args, voice_narrator)
        voice_female = _coerce_vieneu_voice_runtime_value(args, voice_female)
        voice_male = _coerce_vieneu_voice_runtime_value(args, voice_male)
        voice_en_narrator = _coerce_vieneu_voice_runtime_value(args, voice_en_narrator)
        voice_en_female = _coerce_vieneu_voice_runtime_value(args, voice_en_female)
        voice_en_male = _coerce_vieneu_voice_runtime_value(args, voice_en_male)

    return VoiceRuntimeMaps(
        voice_map_vi={
            "narrator": voice_narrator,
            "female": voice_female,
            "male": voice_male,
        },
        voice_map_en={
            "narrator": voice_en_narrator,
            "female": voice_en_female,
            "male": voice_en_male,
        },
    )
