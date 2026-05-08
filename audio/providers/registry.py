from __future__ import annotations

from importlib import import_module

from audio.provider_catalog import get_provider_choice_group
from audio.providers.base import TtsProviderDescriptor, normalize_provider_token

_CHOICES = get_provider_choice_group("audio_tts")
DEFAULT_TTS_PROVIDER = _CHOICES.default_provider_id


def _discover_provider_descriptors() -> dict[str, TtsProviderDescriptor]:
    import audio.providers as providers_pkg

    descriptors: dict[str, TtsProviderDescriptor] = {}
    for name in _CHOICES.provider_ids:
        module = import_module(f"{providers_pkg.__name__}.{name}")
        descriptor = getattr(module, "DESCRIPTOR", None)
        if isinstance(descriptor, TtsProviderDescriptor):
            descriptors[descriptor.provider_id] = descriptor
    return dict(sorted(descriptors.items(), key=lambda item: (_CHOICES.sort_index(item[0]), item[1].sort_order, item[0])))


def get_tts_provider_descriptors() -> dict[str, TtsProviderDescriptor]:
    return _discover_provider_descriptors()


def get_tts_provider_choices() -> list[str]:
    return list(get_tts_provider_descriptors())


def normalize_tts_provider(value: object) -> str:
    descriptors = get_tts_provider_descriptors()
    aliases: dict[str, str] = {}
    for provider_id, descriptor in descriptors.items():
        aliases[normalize_provider_token(provider_id)] = provider_id
        aliases[normalize_provider_token(descriptor.label)] = provider_id
        for alias in descriptor.aliases:
            aliases[normalize_provider_token(alias)] = provider_id
    normalized = normalize_provider_token(value or DEFAULT_TTS_PROVIDER)
    fallback = DEFAULT_TTS_PROVIDER if DEFAULT_TTS_PROVIDER in descriptors else next(iter(descriptors))
    return aliases.get(normalized, fallback)


def get_tts_provider_descriptor(provider: object) -> TtsProviderDescriptor:
    descriptors = get_tts_provider_descriptors()
    return descriptors[normalize_tts_provider(provider)]
