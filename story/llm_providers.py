from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml

from story.provider_catalog import get_provider_choice_group


@dataclass(frozen=True)
class LLMModelProfile:
    profile_id: str
    label: str
    description: str
    base_url_env: str
    base_url_fallback: str
    model_env: str
    model_fallback: str
    api_key_env: str
    api_key_fallback: str = ""

    @property
    def default_base_url(self) -> str:
        return os.getenv(self.base_url_env, self.base_url_fallback)

    @property
    def default_model(self) -> str:
        return os.getenv(self.model_env, self.model_fallback)

    @property
    def default_api_key(self) -> str:
        return os.getenv(self.api_key_env, self.api_key_fallback)


@dataclass(frozen=True)
class LLMProviderPreset:
    provider_id: str
    label: str
    description: str
    default_profile_id: str
    requires_api_key: bool
    profiles: tuple[LLMModelProfile, ...]


class LLMProviderConfigError(ValueError):
    pass


from story.paths import resolve_assets_root

_CHOICES = get_provider_choice_group("story_llm")
_MODULES_ROOT = resolve_assets_root() / "llm"
DEFAULT_PROVIDER_ID = _CHOICES.default_provider_id
DEFAULT_PROVIDER_ORDER = _CHOICES.provider_ids
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ALLOWED_TOP_KEYS = {"providers"}
_ALLOWED_PROVIDER_KEYS = {
    "provider_id",
    "label",
    "description",
    "default_profile_id",
    "requires_api_key",
    "profiles",
}
_ALLOWED_PROFILE_KEYS = {
    "profile_id",
    "label",
    "description",
    "base_url_env",
    "base_url_fallback",
    "model_env",
    "model_fallback",
    "api_key_env",
    "api_key_fallback",
}


def _require_mapping(value: Any, *, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LLMProviderConfigError(f"{where} must be an object")
    return value


def _require_str(data: Mapping[str, Any], key: str, *, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LLMProviderConfigError(f"{where}: field '{key}' must be a non-empty string")
    return value.strip()


def _optional_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LLMProviderConfigError(f"field '{key}' must be a string when provided")
    return value.strip()


def _validate_no_unknown_keys(data: Mapping[str, Any], *, allowed: set[str], where: str) -> None:
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        raise LLMProviderConfigError(f"{where}: unknown field(s): {', '.join(unknown)}")


def _validate_id(value: str, *, kind: str, where: str) -> str:
    if not _ID_RE.fullmatch(value):
        raise LLMProviderConfigError(
            f"{where}: {kind} '{value}' must match pattern {_ID_RE.pattern}"
        )
    return value


def _validate_env_name(value: str, *, key: str, where: str) -> str:
    if not _ENV_NAME_RE.fullmatch(value):
        raise LLMProviderConfigError(
            f"{where}: field '{key}' must look like an uppercase env var name"
        )
    return value


def _validate_base_url(value: str, *, where: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LLMProviderConfigError(f"{where}: base_url_fallback must be a valid http/https URL")
    return value


def validate_provider_config_data(raw: Any) -> tuple[LLMProviderPreset, ...]:
    root = _require_mapping(raw or {}, where="providers config")
    _validate_no_unknown_keys(root, allowed=_ALLOWED_TOP_KEYS, where="providers config")
    providers_raw = root.get("providers")
    if not isinstance(providers_raw, list) or not providers_raw:
        raise LLMProviderConfigError("provider config must contain a non-empty 'providers' list")

    providers: list[LLMProviderPreset] = []
    seen_provider_ids: set[str] = set()
    seen_labels: set[str] = set()
    for idx, item in enumerate(providers_raw, start=1):
        item = _require_mapping(item, where=f"provider[{idx}]")
        where = f"provider[{idx}]"
        _validate_no_unknown_keys(item, allowed=_ALLOWED_PROVIDER_KEYS, where=where)
        provider_id = _validate_id(_require_str(item, "provider_id", where=where), kind="provider_id", where=where)
        if provider_id in seen_provider_ids:
            raise LLMProviderConfigError(f"Duplicate provider_id: {provider_id}")
        seen_provider_ids.add(provider_id)
        label = _require_str(item, "label", where=where)
        if label in seen_labels:
            raise LLMProviderConfigError(f"Duplicate provider label: {label}")
        seen_labels.add(label)
        description = _require_str(item, "description", where=where)
        default_profile_id = _validate_id(
            _require_str(item, "default_profile_id", where=where), kind="default_profile_id", where=where
        )
        requires_api_key = item.get("requires_api_key", False)
        if not isinstance(requires_api_key, bool):
            raise LLMProviderConfigError(f"{where}: 'requires_api_key' must be a boolean")
        profiles_raw = item.get("profiles")
        if not isinstance(profiles_raw, list) or not profiles_raw:
            raise LLMProviderConfigError(f"{where}: 'profiles' must be a non-empty list")

        profiles: list[LLMModelProfile] = []
        seen_profile_ids: set[str] = set()
        seen_profile_labels: set[str] = set()
        for pidx, profile_raw in enumerate(profiles_raw, start=1):
            profile_raw = _require_mapping(profile_raw, where=f"{where}.profiles[{pidx}]")
            pwhere = f"{where}.profiles[{pidx}]"
            _validate_no_unknown_keys(profile_raw, allowed=_ALLOWED_PROFILE_KEYS, where=pwhere)
            profile_id = _validate_id(_require_str(profile_raw, "profile_id", where=pwhere), kind="profile_id", where=pwhere)
            if profile_id in seen_profile_ids:
                raise LLMProviderConfigError(f"Duplicate profile_id '{profile_id}' in provider '{provider_id}'")
            seen_profile_ids.add(profile_id)
            profile_label = _require_str(profile_raw, "label", where=pwhere)
            if profile_label in seen_profile_labels:
                raise LLMProviderConfigError(f"Duplicate profile label '{profile_label}' in provider '{provider_id}'")
            seen_profile_labels.add(profile_label)
            base_url_env = _validate_env_name(_require_str(profile_raw, "base_url_env", where=pwhere), key="base_url_env", where=pwhere)
            model_env = _validate_env_name(_require_str(profile_raw, "model_env", where=pwhere), key="model_env", where=pwhere)
            api_key_env = _validate_env_name(_require_str(profile_raw, "api_key_env", where=pwhere), key="api_key_env", where=pwhere)
            base_url_fallback = _optional_str(profile_raw, "base_url_fallback")
            if base_url_fallback:
                _validate_base_url(base_url_fallback, where=pwhere)
            model_fallback = _optional_str(profile_raw, "model_fallback")
            api_key_fallback = _optional_str(profile_raw, "api_key_fallback")
            if requires_api_key and not api_key_fallback and api_key_env == "":
                raise LLMProviderConfigError(f"{pwhere}: remote provider must declare api_key_env or api_key_fallback")
            profiles.append(
                LLMModelProfile(
                    profile_id=profile_id,
                    label=profile_label,
                    description=_require_str(profile_raw, "description", where=pwhere),
                    base_url_env=base_url_env,
                    base_url_fallback=base_url_fallback,
                    model_env=model_env,
                    model_fallback=model_fallback,
                    api_key_env=api_key_env,
                    api_key_fallback=api_key_fallback,
                )
            )
        if default_profile_id not in seen_profile_ids:
            raise LLMProviderConfigError(
                f"Provider '{provider_id}' default_profile_id '{default_profile_id}' does not exist in profiles"
            )
        providers.append(
            LLMProviderPreset(
                provider_id=provider_id,
                label=label,
                description=description,
                default_profile_id=default_profile_id,
                requires_api_key=requires_api_key,
                profiles=tuple(profiles),
            )
        )
    return tuple(providers)


def _provider_items_from_module_data(raw: Any, *, path: Path) -> list[dict[str, Any]]:
    data = _require_mapping(raw or {}, where=f"provider module {path}")
    if "providers" in data:
        wrapped = validate_provider_config_data(data)
        return [
            {
                "provider_id": item.provider_id,
                "label": item.label,
                "description": item.description,
                "default_profile_id": item.default_profile_id,
                "requires_api_key": item.requires_api_key,
                "profiles": [
                    {
                        "profile_id": profile.profile_id,
                        "label": profile.label,
                        "description": profile.description,
                        "base_url_env": profile.base_url_env,
                        "base_url_fallback": profile.base_url_fallback,
                        "model_env": profile.model_env,
                        "model_fallback": profile.model_fallback,
                        "api_key_env": profile.api_key_env,
                        "api_key_fallback": profile.api_key_fallback,
                    }
                    for profile in item.profiles
                ],
            }
            for item in wrapped
        ]
    return [data]


@lru_cache(maxsize=1)
def _load_provider_presets() -> tuple[LLMProviderPreset, ...]:
    return load_provider_presets_from_modules_dir(_MODULES_ROOT)


def clear_provider_preset_cache() -> None:
    _load_provider_presets.cache_clear()


def load_provider_presets_from_path(path: Path | str) -> tuple[LLMProviderPreset, ...]:
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise LLMProviderConfigError(f"Missing provider config file: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return validate_provider_config_data(raw)


def load_provider_presets_from_modules_dir(path: Path | str) -> tuple[LLMProviderPreset, ...]:
    modules_root = Path(path).resolve()
    if not modules_root.exists() or not modules_root.is_dir():
        raise LLMProviderConfigError(f"Missing provider modules directory: {modules_root}")
    module_paths: list[Path] = []
    for provider_id in DEFAULT_PROVIDER_ORDER:
        yml_path = modules_root / f"{provider_id}.yml"
        yaml_path = modules_root / f"{provider_id}.yaml"
        if yml_path.is_file():
            module_paths.append(yml_path)
        elif yaml_path.is_file():
            module_paths.append(yaml_path)
    if not module_paths:
        raise LLMProviderConfigError(f"Provider modules directory is empty: {modules_root}")
    provider_items: list[dict[str, Any]] = []
    for module_path in module_paths:
        raw = yaml.safe_load(module_path.read_text(encoding="utf-8")) or {}
        provider_items.extend(_provider_items_from_module_data(raw, path=module_path))
    providers = validate_provider_config_data({"providers": provider_items})
    order = {provider_id: idx for idx, provider_id in enumerate(DEFAULT_PROVIDER_ORDER)}
    return tuple(
        sorted(
            providers,
            key=lambda item: (order.get(item.provider_id, len(order)), item.label.lower(), item.provider_id),
        )
    )


def validate_provider_config_file(path: Path | str) -> tuple[LLMProviderPreset, ...]:
    return load_provider_presets_from_path(path)


def validate_provider_modules_dir(path: Path | str | None = None) -> tuple[LLMProviderPreset, ...]:
    return load_provider_presets_from_modules_dir(path or _MODULES_ROOT)


def list_provider_presets() -> list[LLMProviderPreset]:
    return list(_load_provider_presets())


def list_provider_ids() -> list[str]:
    return [item.provider_id for item in _load_provider_presets()]


def get_provider_preset(provider_id: str | None) -> LLMProviderPreset:
    provider_key = str(provider_id or DEFAULT_PROVIDER_ID).strip()
    for item in _load_provider_presets():
        if item.provider_id == provider_key:
            return item
    for item in _load_provider_presets():
        if item.provider_id == DEFAULT_PROVIDER_ID:
            return item
    return _load_provider_presets()[0]


def provider_label(provider_id: str | None) -> str:
    return get_provider_preset(provider_id).label


def provider_description(provider_id: str | None) -> str:
    return get_provider_preset(provider_id).description


def list_model_profiles(provider_id: str | None) -> list[LLMModelProfile]:
    return list(get_provider_preset(provider_id).profiles)


def list_model_profile_ids(provider_id: str | None) -> list[str]:
    return [item.profile_id for item in list_model_profiles(provider_id)]


def get_model_profile(provider_id: str | None, profile_id: str | None = None) -> LLMModelProfile:
    provider = get_provider_preset(provider_id)
    target_id = str(profile_id or provider.default_profile_id).strip() or provider.default_profile_id
    for item in provider.profiles:
        if item.profile_id == target_id:
            return item
    for item in provider.profiles:
        if item.profile_id == provider.default_profile_id:
            return item
    return provider.profiles[0]


def model_profile_label(provider_id: str | None, profile_id: str | None) -> str:
    return get_model_profile(provider_id, profile_id).label


def model_profile_description(provider_id: str | None, profile_id: str | None) -> str:
    return get_model_profile(provider_id, profile_id).description


def build_provider_settings(provider_id: str | None, profile_id: str | None = None) -> dict[str, str]:
    provider = get_provider_preset(provider_id)
    profile = get_model_profile(provider.provider_id, profile_id)
    return {
        "llm_provider": provider.provider_id,
        "llm_provider_label": provider.label,
        "llm_profile": profile.profile_id,
        "llm_profile_label": profile.label,
        "base_url": profile.default_base_url,
        "model": profile.default_model,
        "api_key": profile.default_api_key,
    }


def infer_provider_id(base_url: str | None, api_key: str | None = None) -> str:
    url = str(base_url or "").strip().lower()
    key = str(api_key or "").strip()
    if "api.openai.com" in url:
        return "openai_chatgpt"
    if ":23333" in url:
        return "lmdeploy"
    if any(token in url for token in ("localhost", "127.0.0.1", "0.0.0.0")):
        return "lm_studio"
    if key and key != "not-needed":
        return "custom_compatible"
    return DEFAULT_PROVIDER_ID
