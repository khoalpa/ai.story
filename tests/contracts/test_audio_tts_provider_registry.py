from __future__ import annotations

import importlib


def test_tts_provider_choices_are_discovered_from_provider_modules() -> None:
    registry = importlib.import_module("audio.tts_provider")

    choices = registry.get_tts_provider_choices()

    assert choices == ["vieneu", "edge"]
    assert registry.normalize_tts_provider("edge-tts") == "edge"
    assert registry.normalize_tts_provider("vie-neu") == "vieneu"


def test_voice_catalog_uses_provider_module_voice_choices() -> None:
    voice_catalog = importlib.import_module("audio.voice_catalog")

    voices = voice_catalog.get_voice_choices(tts_provider="edge", lang="vi", role="narrator")

    assert [voice.value for voice in voices] == ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]

