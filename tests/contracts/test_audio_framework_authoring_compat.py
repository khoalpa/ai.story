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
                "environment": "none",
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


def test_audio_validator_accepts_story_quality_commitment_meta_object() -> None:
    from audio.audio_story_spec import validate_canonical_authoring

    authoring = _framework_authoring()
    authoring["meta"]["language"] = "vi"
    authoring["meta"]["story_quality_commitment"] = {
        "schema_version": "1.1",
        "created_by_prompt_version": "3.11.3",
        "minimum_verifier_version": "3.8.6",
        "final_script_text_digest_sha256": "abc123",
        "recomputable_metrics": {"total_words": 42},
    }
    authoring["script"][0]["text"] = "Một câu hợp lệ."

    assert validate_canonical_authoring(authoring) == []


def test_audio_validator_rejects_non_object_story_quality_commitment() -> None:
    from audio.audio_story_spec import validate_canonical_authoring

    authoring = _framework_authoring()
    authoring["meta"]["language"] = "vi"
    authoring["meta"]["story_quality_commitment"] = "invalid"
    authoring["script"][0]["text"] = "Một câu hợp lệ."

    assert "meta.story_quality_commitment must be an object." in validate_canonical_authoring(authoring)


def test_audio_validator_accepts_characters_and_schema_version_at_root() -> None:
    from audio.audio_story_spec import validate_canonical_authoring

    authoring = _framework_authoring()
    authoring["meta"]["language"] = "vi"
    authoring["script"][0]["text"] = "Một câu hợp lệ."
    authoring["characters"] = [{"name": "Mi"}]
    authoring["schema_version"] = "1.0"

    assert validate_canonical_authoring(authoring) == []


def test_audio_validator_ignores_length_min_item_count_rule() -> None:
    from audio.audio_story_spec import validate_canonical_authoring

    authoring = _framework_authoring()
    authoring["meta"]["language"] = "vi"
    authoring["meta"]["length_min"] = 8
    authoring["meta"]["length_max"] = 10
    authoring["script"][0]["text"] = "Một câu hợp lệ."

    assert validate_canonical_authoring(authoring) == []


def test_audio_gui_conversion_normalizes_framework_language_and_sentences() -> None:
    from audio.gui.helpers import convert_canonical_to_plain_text

    plain = convert_canonical_to_plain_text(json.dumps(_framework_authoring(), ensure_ascii=False))

    assert "Câu đầu tiên." in plain
    assert "Câu thứ hai." in plain


def test_audio_gui_converts_canonical_to_raw_text() -> None:
    from audio.gui.helpers import convert_canonical_to_raw_text

    raw = convert_canonical_to_raw_text(json.dumps(_framework_authoring(), ensure_ascii=False))

    assert raw.splitlines()[:2] == ["Câu đầu tiên.", "Câu thứ hai."]
    assert "[NARRATOR]" not in raw
    assert "SCRIPT:" not in raw
