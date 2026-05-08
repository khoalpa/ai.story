from __future__ import annotations

from audio.providers.base import TtsProviderDescriptor
from audio.providers.registry import (
    DEFAULT_TTS_PROVIDER,
    get_tts_provider_choices,
    get_tts_provider_descriptor,
    get_tts_provider_descriptors,
    normalize_tts_provider,
)

TTS_PROVIDER_VIENEU = "vieneu"
TTS_PROVIDER_EDGE = "edge"
SUPPORTED_TTS_PROVIDERS = tuple(get_tts_provider_choices())
TTS_PROVIDER_DESCRIPTORS: dict[str, TtsProviderDescriptor] = get_tts_provider_descriptors()
