from __future__ import annotations

import json

import pytest

from audio.story_package_v416 import (
    parse_story_text,
    raw_script,
    render_plain_script,
    validate_story,
)


@pytest.mark.parametrize("raw", [
    '{}', '[]', '{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e400}', '\ufeff{}', '{',
])
def test_story_parser_rejects_noncanonical_json(raw):
    with pytest.raises(ValueError):
        parse_story_text(raw)


@pytest.mark.parametrize("path,value,message", [
    (("meta",), [], "meta"),
    (("meta", "title"), " ", "meta.title"),
    (("meta", "series"), [], "meta.series"),
    (("meta", "episode"), True, "meta.episode"),
    (("meta", "profile"), [], "meta.profile"),
    (("meta", "age_band"), {}, "meta.age_band"),
    (("meta", "target_minutes"), False, "meta.target_minutes"),
    (("meta", "estimated_minutes"), -1, "meta.estimated_minutes"),
    (("meta", "tags"), ["rain", "RAIN"], "meta.tags"),
    (("meta", "tags"), [None], "meta.tags"),
    (("characters",), [], "characters"),
    (("characters", 0), None, "characters[1]"),
    (("characters", 0, "character_id"), "bad", "character_id"),
    (("characters", 0, "age"), -1, ".age"),
    (("characters", 0, "name"), "", ".name"),
    (("outline",), None, "outline"),
    (("outline", 0), {}, "outline[1]"),
    (("outline", 0, "scene_id"), "sc999", ".scene_id"),
    (("outline", 0, "summary"), None, ".summary"),
    (("outline", 0, "setup_or_payoff"), [], ".setup_or_payoff"),
    (("script",), None, "script"),
    (("script", 0), None, "script[1]"),
    (("script", 0, "id"), "s9999", ".id"),
    (("script", 0, "zone"), [], ".zone"),
    (("script", 0, "scene_id"), "unknown", ".scene_id"),
    (("script", 0, "speaker"), "unknown", ".speaker"),
    (("script", 0, "text"), " ", ".text"),
    (("script", 0, "emotion"), None, ".emotion"),
    (("script", 0, "speed"), "1", ".speed"),
    (("script", 0, "pause_ms"), True, ".pause_ms"),
    (("script", 0, "ambience"), [], ".ambience"),
])
def test_story_rejects_invalid_field_without_crashing(sample_story_text, path, value, message):
    story = json.loads(sample_story_text)
    parent = story
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert any(message in error for error in validate_story(story))
    with pytest.raises(ValueError, match="v4.1.6"):
        parse_story_text(json.dumps(story, ensure_ascii=False))


def test_story_rejects_duplicate_characters_and_reopened_scenes(sample_story_text):
    story = json.loads(sample_story_text)
    story["characters"].append(dict(story["characters"][0]))
    story["script"][-1]["scene_id"] = story["script"][0]["scene_id"]
    story["script"][-1]["zone"] = "GREETING"
    errors = validate_story(story)
    assert any("duy nhất" in error for error in errors)
    assert any("đã đóng" in error for error in errors)
    assert any("zone đi lùi" in error for error in errors)
    for render in (raw_script, render_plain_script):
        with pytest.raises(ValueError, match="v4.1.6"):
            render(story)


def test_story_root_must_be_an_object():
    assert validate_story(None) == ["Root phải là object."]
