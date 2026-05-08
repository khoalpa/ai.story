from __future__ import annotations

from audio.providers.base import TtsProviderDescriptor, VoiceChoice

PROVIDER_ID = "edge"


def get_voice_choices(*, lang: str, role: str) -> tuple[VoiceChoice, ...]:
    normalized_lang = str(lang or "vi").strip().lower() or "vi"
    normalized_role = str(role or "narrator").strip().lower() or "narrator"
    filtered = [item for item in VOICE_CHOICES if item.lang == normalized_lang and item.role == normalized_role]
    if filtered:
        return tuple(filtered)
    return tuple(item for item in VOICE_CHOICES if item.lang == normalized_lang)


DESCRIPTOR = TtsProviderDescriptor(
    provider_id=PROVIDER_ID,
    label="Edge TTS",
    description="Cloud voice quality tot, dung voice ID kieu vi-VN-HoaiMyNeural / en-US-AriaNeural.",
    requires_network=True,
    optional_dependency="edge_tts",
    aliases=("edge", "edgetts", "edgecli"),
    sort_order=20,
    voice_choices=lambda lang, role: get_voice_choices(lang=lang, role=role),
)

VOICE_CHOICES: tuple[VoiceChoice, ...] = (
    VoiceChoice("vi-VN-HoaiMyNeural", "HoaiMy (VI - nu)", "vi", "female"),
    VoiceChoice("vi-VN-NamMinhNeural", "NamMinh (VI - nam)", "vi", "male"),
    VoiceChoice("vi-VN-HoaiMyNeural", "HoaiMy (VI - ke chuyen)", "vi", "narrator"),
    VoiceChoice("vi-VN-NamMinhNeural", "NamMinh (VI - ke chuyen)", "vi", "narrator"),
    VoiceChoice("en-US-AriaNeural", "Aria (EN - female)", "en", "female"),
    VoiceChoice("en-US-GuyNeural", "Guy (EN - male)", "en", "male"),
    VoiceChoice("en-US-AriaNeural", "Aria (EN - narrator)", "en", "narrator"),
    VoiceChoice("en-US-GuyNeural", "Guy (EN - narrator)", "en", "narrator"),
)
