from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO

import pytest

from studio.prompt_contract import load_prompt_contract
from studio.video_prompt_projection import (
    build_prompt_package,
    canonical_json_bytes,
    project_video_prompts,
    prompt_text,
    validate_projection,
)
from studio.video_prompt_validation import (
    canonical_output_digest,
    normalize_video_prompt_plan,
    validate_video_prompt_plan,
)


def test_projection_is_deterministic_and_bound_to_canonical_bytes() -> None:
    contract = load_prompt_contract()
    plan = {"schema_version": contract.video_prompt_schema_version, "project": {"title": "T"}, "global_continuity_lock": {}, "clips": []}
    source = canonical_json_bytes(plan)
    name, first = project_video_prompts(plan, "VEO", source_bytes=source, contract=contract)
    _, second = project_video_prompts(plan, "VEO", source_bytes=source, contract=contract)
    document = json.loads(first)
    assert name == "video_prompts.veo.json"
    assert first == second
    assert document["projection_binding"]["source_digest_sha256"] == hashlib.sha256(source).hexdigest()
    assert validate_projection(document, plan, source_bytes=source, contract=contract)


def test_projection_becomes_stale_when_canonical_bytes_change() -> None:
    plan = {"schema_version": "1.0", "project": {}, "global_continuity_lock": {}, "clips": []}
    source = canonical_json_bytes(plan)
    _, raw = project_video_prompts(plan, "FLOW", source_bytes=source)
    assert not validate_projection(json.loads(raw), plan, source_bytes=source + b" ")


def test_output_digest_uses_null_digest_field() -> None:
    plan = {"validation": {"output_digest_sha256": "placeholder"}}
    expected = hashlib.sha256(canonical_json_bytes({"validation": {"output_digest_sha256": None}})).hexdigest()
    assert canonical_output_digest(plan) == expected


def test_validator_rejects_noncanonical_root() -> None:
    result = validate_video_prompt_plan({"schema_version": "0.9"})
    assert result["status"] == "FAIL"
    assert result["errors"]


def test_normalizer_repairs_ratio_source_digest_and_output_digest_without_claiming_pass() -> None:
    story = {"script": [{"text": "one two three"}, {"text": "four five"}]}
    plan = {
        "generator_target": {"capability_profile": {"aspect_ratio": "16:9"}},
        "project": {"coverage_mode": "FULL_STORY"},
        "clips": [{
            "aspect_ratio": "16:9",
            "source_script": {
                "start_item_index": 0, "start_word_offset": 0,
                "end_item_index": 1, "end_word_offset": 2,
                "pause_only": False, "source_text_digest_sha256": "wrong",
            },
        }],
        "validation": {"schema_status": "NOT_VERIFIED", "output_digest_sha256": "wrong"},
    }

    normalized = normalize_video_prompt_plan(plan, story)

    assert normalized["generator_target"]["capability_profile"]["aspect_ratio"] == "LANDSCAPE_16_9"
    assert normalized["clips"][0]["aspect_ratio"] == "LANDSCAPE_16_9"
    assert normalized["clips"][0]["source_script"]["source_text_digest_sha256"] != "wrong"
    assert normalized["validation"]["schema_status"] == "NOT_VERIFIED"
    assert normalized["validation"]["output_digest_sha256"] == canonical_output_digest(normalized)
    assert plan["clips"][0]["aspect_ratio"] == "16:9"


def test_chained_previous_clip_resets_at_scene_boundary() -> None:
    def clip(identifier: str, sequence: int, scene: str, previous: str | None) -> dict:
        return {
            "clip_id": identifier, "sequence_index": sequence, "derived_scene_id": scene,
            "source_script": {}, "generation_variants": {"requested_continuity_mode": "CHAINED_LAST_FRAME"},
            "reference_inputs": {"previous_clip_id": previous},
        }

    scene_break = {"clips": [clip("clip_0001", 1, "scene_0001", None),
                              clip("clip_0002", 2, "scene_0002", None)]}
    within_scene = {"clips": [clip("clip_0001", 1, "scene_0001", None),
                               clip("clip_0002", 2, "scene_0001", None)]}

    assert not any("previous_clip_id" in error for error in validate_video_prompt_plan(scene_break)["errors"])
    assert any("previous_clip_id" in error for error in validate_video_prompt_plan(within_scene)["errors"])


def export_plan() -> dict:
    return {
        "schema_version": "1.0",
        "generator_target": {
            "preferred_model": "veo-model",
            "capability_profile": {
                "reference_images": {"status": "NOT_VERIFIED"},
                "first_last_frame": {"status": "NOT_VERIFIED"},
                "video_extension": {"status": "NOT_VERIFIED"},
            },
        },
        "project": {"title": "Demo"},
        "global_continuity_lock": {},
        "clips": [
            {
                "clip_id": "clip_0001",
                "sequence_index": 1,
                "prompt": "A quiet opening shot",
                "audio_prompt": "Soft rain",
                "avoid": ["text", "logo"],
                "duration_seconds": 8,
                "aspect_ratio": "16:9",
                "reference_inputs": {
                    "zone_reference_frame": "landscape/opening.png",
                    "primary_frame": None,
                    "target_last_frame": None,
                    "character_images": ["characters/hero.png"],
                },
                "generation_variants": {"requested_continuity_mode": "INDEPENDENT"},
                "continuity_in": {},
                "continuity_out": {},
                "transition_type": "CUT",
            },
            {
                "clip_id": "clip_0002",
                "sequence_index": 2,
                "prompt": "The hero enters the room",
                "audio_prompt": "Footsteps",
                "avoid": [],
                "duration_seconds": 8,
                "aspect_ratio": "16:9",
                "reference_inputs": {
                    "zone_reference_frame": "landscape/opening.png",
                    "primary_frame": None,
                    "target_last_frame": None,
                    "character_images": ["characters/hero.png"],
                },
                "generation_variants": {"requested_continuity_mode": "CHAINED_LAST_FRAME"},
                "continuity_in": {},
                "continuity_out": {},
                "transition_type": "CUT",
            },
        ],
    }


@pytest.mark.parametrize("target", ["VEO", "FLOW", "GENERIC"])
def test_prompt_package_is_deterministic_and_self_verifying(target: str) -> None:
    plan = export_plan()
    source = canonical_json_bytes(plan)
    name, first = build_prompt_package(plan, target, source_bytes=source)
    _, second = build_prompt_package(plan, target, source_bytes=source)
    assert name == f"video_prompts.{target.lower()}.zip"
    assert first == second
    with zipfile.ZipFile(BytesIO(first)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["source_digest_sha256"] == hashlib.sha256(source).hexdigest()
        assert archive.read("canonical/video_prompts.json") == source
        assert "prompts/clip_0001.json" in archive.namelist()
        for row in manifest["files"]:
            raw = archive.read(row["path"])
            assert len(raw) == row["size_bytes"]
            assert hashlib.sha256(raw).hexdigest() == row["sha256"]


def test_flow_projection_contains_last_frame_dependency() -> None:
    _, raw = project_video_prompts(export_plan(), "FLOW")
    payload = json.loads(raw)["projection"]["target_payload"]
    assert payload["edges"] == [{
        "from": "clip_0001",
        "to": "clip_0002",
        "binding": "last_frame_to_first_frame",
    }]


def test_text_export_keeps_prompt_avoid_and_references() -> None:
    text = prompt_text(export_plan(), "GENERIC").decode("utf-8")
    assert "[clip_0001] GENERIC" in text
    assert "A quiet opening shot" in text
    assert "text, logo" in text
    assert "characters/hero.png" in text


def test_export_rejects_unknown_adapter_and_mismatched_source() -> None:
    plan = export_plan()
    with pytest.raises(ValueError, match="adapter deterministic"):
        project_video_prompts(plan, "UNKNOWN")
    with pytest.raises(ValueError, match="không tương đương"):
        build_prompt_package(plan, "VEO", source_bytes=b"{}")
