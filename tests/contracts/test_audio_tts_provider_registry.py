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


def test_vieneu_standard_narrator_prefers_doan_for_legacy_thuc_doan_default() -> None:
    voice_catalog = importlib.import_module("audio.voice_catalog")

    selected = voice_catalog.resolve_voice_selection(
        "Thuc Doan",
        tts_provider="vieneu",
        lang="vi",
        role="narrator",
        fallback="Thuc Doan",
    )

    assert selected == "Doan"


def test_vieneu_en_defaults_prefer_doan_when_edge_defaults_are_not_available() -> None:
    voice_catalog = importlib.import_module("audio.voice_catalog")

    selected_narrator = voice_catalog.resolve_voice_selection(
        "en-US-AriaNeural",
        tts_provider="vieneu",
        lang="en",
        role="narrator",
        fallback="Doan",
    )
    selected_female = voice_catalog.resolve_voice_selection(
        "en-US-JennyNeural",
        tts_provider="vieneu",
        lang="en",
        role="female",
        fallback="Doan",
    )

    assert selected_narrator == "Doan"
    assert selected_female == "Doan"

