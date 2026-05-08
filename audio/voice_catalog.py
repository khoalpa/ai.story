from __future__ import annotations

from audio.tts_provider import TTS_PROVIDER_VIENEU, get_tts_provider_descriptor, normalize_tts_provider
from audio.providers.base import VoiceChoice


def find_local_voice_notice(*, tts_provider: str, lang: str) -> str | None:
    descriptor = get_tts_provider_descriptor(tts_provider)
    if descriptor.local_voice_notice is None:
        return None
    return descriptor.local_voice_notice(str(lang or "vi").strip().lower() or "vi")


def get_voice_choices(*, tts_provider: str, lang: str, role: str) -> tuple[VoiceChoice, ...]:
    descriptor = get_tts_provider_descriptor(tts_provider)
    if descriptor.voice_choices is None:
        return tuple()
    norm_lang = str(lang or "vi").strip().lower() or "vi"
    norm_role = str(role or "narrator").strip().lower() or "narrator"
    return descriptor.voice_choices(norm_lang, norm_role)


def get_voice_values(*, tts_provider: str, lang: str, role: str) -> tuple[str, ...]:
    return tuple(item.value for item in get_voice_choices(tts_provider=tts_provider, lang=lang, role=role))


def resolve_voice_selection(current_value: str, *, tts_provider: str, lang: str, role: str, fallback: str) -> str:
    desired = str(current_value or "").strip()
    choices = get_voice_choices(tts_provider=tts_provider, lang=lang, role=role)
    values = [item.value for item in choices]
    if desired and desired in values:
        return desired
    provider = normalize_tts_provider(tts_provider)
    if provider == TTS_PROVIDER_VIENEU and desired and choices:
        from audio.providers.vieneu import migrate_vieneu_legacy_voice_id

        migrated = migrate_vieneu_legacy_voice_id(desired, tuple((item.label, item.value) for item in choices))
        if migrated in values:
            return migrated
    fallback_value = str(fallback or "").strip()
    if fallback_value in values:
        return fallback_value
    if choices:
        return choices[0].value
    return fallback_value or desired
