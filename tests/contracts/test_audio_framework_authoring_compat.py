from __future__ import annotations

import json


def _framework_authoring() -> dict:
    from audio.audio_story_spec import ALLOWED_SCRIPT_ZONES, OUTLINE_KEYS

    return {
        "meta": {
            "title": "Framework Story",
            "series": "",
            "episode": "",
            "author": "AI Story",
            "channel": "Audio Story",
            "target": "Adult listeners",
            "length_min": 0,
            "length_max": 1,
            "language": "Vietnamese",
            "genre": "Drama",
            "audience": "Adult",
            "tone": "Warm",
            "tags": ["framework"],
            "profile": "ADULT_STANDARD",
            "framework_version": "4.0",
            "story_signature": "adult_standard-framework-story",
            "art_direction_id": "AS-FRAMEWORK-01",
        },
        "outline": {key: f"{key} beat" for key in OUTLINE_KEYS},
        "script": [
            {
                "zone": zone,
                "environment": "",
                "voice": "NARRATOR",
                "speed": "NORMAL",
                "lang": "VI",
                "text": "Câu đầu tiên. Câu thứ hai." if index == 1 else f"Câu ở vùng {index}.",
            }
            for index, zone in enumerate(ALLOWED_SCRIPT_ZONES, start=1)
        ],
    }


def test_audio_validator_accepts_framework_meta_extensions() -> None:
    from audio.audio_story_spec import validate_canonical_authoring

    authoring = _framework_authoring()
    authoring["meta"]["language"] = "vi"
    authoring["script"][0]["text"] = "Một câu hợp lệ."

    assert validate_canonical_authoring(authoring) == []


def test_audio_gui_conversion_normalizes_framework_language_and_sentences() -> None:
    from audio.gui.helpers import convert_canonical_to_plain_text

    plain = convert_canonical_to_plain_text(json.dumps(_framework_authoring(), ensure_ascii=False))

    assert "Câu đầu tiên." in plain
    assert "Câu thứ hai." in plain
