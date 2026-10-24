from __future__ import annotations

import json
import math

import pytest

from studio.video_prompt_validation import validate_video_prompt_plan


@pytest.fixture
def video_plan():
    return {
        "schema_version": "4.1.3", "source_mode": "STORY_ONLY", "target_model": "generic",
        "coverage": "FULL_STORY", "timing_basis": "ESTIMATED", "timing_config": {}, "limitations": [],
        "clips": [{"clip_id": "clip_0001", "source_spans": [{"script_id": "s0001", "start_char": 0, "end_char": 9}],
                   "narration": "Xin chào.", "estimated_seconds": 2.5, "reference_paths": []}],
    }


@pytest.fixture
def story_members():
    return {"story.json": json.dumps({"script": [{"id": "s0001", "text": "Xin chào."}]}).encode()}


def test_full_story_exact_span_and_unavailable_timing(video_plan, story_members):
    result = validate_video_prompt_plan(video_plan, members=story_members)
    assert result["errors"] == []
    assert result["duration"] == 2.5
    video_plan["timing_basis"] = "UNAVAILABLE"
    video_plan["clips"][0]["estimated_seconds"] = None
    result = validate_video_prompt_plan(video_plan, members=story_members)
    assert result["errors"] == []
    assert result["duration"] == 0


@pytest.mark.parametrize("field,value", [
    ("clip_id", "clip_0002"), ("source_spans", None), ("source_spans", [None]),
    ("narration", "Edited words"), ("estimated_seconds", "bad"), ("estimated_seconds", True),
    ("estimated_seconds", -1), ("estimated_seconds", math.inf), ("estimated_seconds", math.nan),
    ("reference_paths", None), ("reference_paths", [None]), ("reference_paths", ["../outside.png"]),
    ("reference_paths", ["missing.png"]),
])
def test_malformed_clip_returns_errors(video_plan, story_members, field, value):
    video_plan["clips"][0][field] = value
    result = validate_video_prompt_plan(video_plan, members=story_members)
    assert result["errors"]
    assert result["continuity_status"] == "NOT_VERIFIED"
    assert math.isfinite(result["duration"])


@pytest.mark.parametrize("field,value", [
    ("schema_version", "old"), ("source_mode", []), ("coverage", None),
    ("timing_basis", []), ("clips", None), ("clips", []), ("clips", [None]),
])
def test_malformed_plan_returns_errors(video_plan, story_members, field, value):
    video_plan[field] = value
    assert validate_video_prompt_plan(video_plan, members=story_members)["errors"]


@pytest.mark.parametrize("field,value", [("script_id", []), ("script_id", "missing"), ("start_char", True),
                                       ("start_char", -1), ("end_char", 99), ("end_char", None)])
def test_invalid_span_offsets_are_not_sliced(video_plan, story_members, field, value):
    video_plan["clips"][0]["source_spans"][0][field] = value
    errors = validate_video_prompt_plan(video_plan, members=story_members)["errors"]
    assert any("offset" in error for error in errors)


def test_full_story_rejects_gaps_and_overlap(video_plan, story_members):
    video_plan["clips"][0]["source_spans"][0]["start_char"] = 1
    assert any("FULL_STORY" in error for error in validate_video_prompt_plan(video_plan, members=story_members)["errors"])
    video_plan["clips"][0]["source_spans"] *= 2
    assert any("FULL_STORY" in error for error in validate_video_prompt_plan(video_plan, members=story_members)["errors"])


@pytest.mark.parametrize("raw", [None, b'{', b'[]', b'{"script":null}', b'{"script":[null]}',
                                  b'{"script":[{"id":[],"text":"x"}]}'])
def test_missing_or_invalid_source_is_rejected(video_plan, raw):
    members = {} if raw is None else {"story.json": raw}
    assert validate_video_prompt_plan(video_plan, members=members)["errors"]


def test_filesystem_references_are_confined_to_project(video_plan, story_members, tmp_path):
    (tmp_path / "story.json").write_bytes(story_members["story.json"])
    (tmp_path / "reference.png").write_bytes(b"present")
    video_plan["clips"][0]["reference_paths"] = ["reference.png"]
    assert not validate_video_prompt_plan(video_plan, root=tmp_path)["errors"]
    video_plan["clips"][0]["reference_paths"] = ["../reference.png"]
    assert validate_video_prompt_plan(video_plan, root=tmp_path)["errors"]
    (tmp_path / "story.json").unlink()
    assert validate_video_prompt_plan(video_plan, root=tmp_path)["errors"]
