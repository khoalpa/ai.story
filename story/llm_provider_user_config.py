from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from story.llm_providers import build_provider_settings, get_model_profile, get_provider_preset

USER_CONFIG_DIR_ENV = "GENERATOR_STORY_USER_CONFIG_DIR"
USER_CONFIG_FILENAME = "llm_user_config.json"
PERSISTED_KEYS = (
    "llm_provider",
    "llm_profile",
    "base_url",
    "model",
    "api_key",
)


class UserLLMConfigError(ValueError):
    pass


def user_config_dir() -> Path:
    override = str(os.getenv(USER_CONFIG_DIR_ENV, "")).strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".generator_story").resolve()


def user_llm_settings_path() -> Path:
    return user_config_dir() / USER_CONFIG_FILENAME


def normalize_persisted_llm_settings(data: Mapping[str, Any] | None) -> dict[str, str]:
    raw = dict(data or {})
    provider_id = str(raw.get("llm_provider") or "").strip() or "lmdeploy"
    provider = get_provider_preset(provider_id)
    profile_id = str(raw.get("llm_profile") or provider.default_profile_id).strip() or provider.default_profile_id
    profile = get_model_profile(provider.provider_id, profile_id)
    defaults = build_provider_settings(provider.provider_id, profile.profile_id)
    return {
        "llm_provider": provider.provider_id,
        "llm_profile": profile.profile_id,
        "base_url": str(raw.get("base_url") or defaults["base_url"] or "").strip(),
        "model": str(raw.get("model") or defaults["model"] or "").strip(),
        "api_key": str(raw.get("api_key") or defaults["api_key"] or "").strip(),
    }


def load_user_llm_settings(path: Path | None = None) -> dict[str, str] | None:
    target = path or user_llm_settings_path()
    if not target.exists():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UserLLMConfigError(f"Invalid JSON in saved LLM user config: {target}") from exc
    if not isinstance(raw, dict):
        raise UserLLMConfigError(f"Saved LLM user config must be a JSON object: {target}")
    return normalize_persisted_llm_settings(raw)


def save_user_llm_settings(settings: Mapping[str, Any], path: Path | None = None) -> Path:
    target = path or user_llm_settings_path()
    normalized = normalize_persisted_llm_settings(settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: normalized[key] for key in PERSISTED_KEYS}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
