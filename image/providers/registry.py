from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from common.provider_catalog import get_provider_choice_group

_CHOICES = get_provider_choice_group("image_sd")


@dataclass(frozen=True)
class SDProvider:
    provider_id: str
    label: str
    renderer: str
    order: int = 100
    requires_base_url: bool = False
    default_base_url: str = ""
    uses_api_key: bool = False
    is_local: bool = False
    is_comfyui: bool = False
    uses_diffusers_runtime: bool = False
    supports_model_browser: bool = False
    show_model_inventory: bool = False
    local_caption: str = ""
    missing_model_requires_warning: bool = False
    default_model: str = ""
    model_provider_id: str | None = None
    preferred_model_suffixes: tuple[str, ...] = ()
    prefer_first_model_as_default: bool = False
    option_groups: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.provider_id

    @property
    def model_scan_provider_id(self) -> str:
        return self.model_provider_id or self.provider_id


def _iter_provider_modules() -> list[str]:
    package_name = __package__
    if not package_name:
        return []
    package = importlib.import_module(package_name)
    module_names: list[str] = []
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name.startswith("_") or module_info.name in _CHOICES.ignored_module_names:
            continue
        if not _CHOICES.is_enabled(module_info.name):
            continue
        module_names.append(f"{package_name}.{module_info.name}")
    return sorted(module_names, key=lambda name: _CHOICES.sort_index(name.rsplit(".", 1)[-1]))


@lru_cache(maxsize=1)
def list_sd_providers() -> tuple[SDProvider, ...]:
    providers: list[SDProvider] = []
    for module_name in _iter_provider_modules():
        module = importlib.import_module(module_name)
        get_provider = getattr(module, "get_provider", None)
        if get_provider is None:
            continue
        provider = get_provider()
        if not isinstance(provider, SDProvider):
            raise TypeError(f"{module_name}.get_provider() must return SDProvider")
        providers.append(provider)
    providers.sort(key=lambda item: (_CHOICES.sort_index(item.provider_id), item.order, item.provider_id))
    return tuple(providers)


def list_sd_provider_ids() -> list[str]:
    return [provider.provider_id for provider in list_sd_providers()]


def get_sd_provider_choices() -> dict[str, str]:
    return {provider.provider_id: provider.label for provider in list_sd_providers()}


def get_sd_provider(provider_id: str | None) -> SDProvider:
    normalized = str(provider_id or "").strip().lower()
    providers = list_sd_providers()
    for provider in providers:
        if provider.provider_id == normalized:
            return provider
    if not normalized and providers:
        return providers[0]
    if not providers:
        raise LookupError("No SD provider modules were discovered.")
    raise LookupError(f"Unknown SD provider: {provider_id}")


def build_provider_payload(provider_id: str | None, values: dict[str, Any]) -> dict[str, Any]:
    provider = get_sd_provider(provider_id)
    payload = dict(values)
    payload["sd_provider"] = provider.provider_id
    payload["sd_provider_option_groups"] = list(provider.option_groups)
    return payload

