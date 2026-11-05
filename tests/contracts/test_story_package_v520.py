from __future__ import annotations

import hashlib
import json
from io import BytesIO

import pytest
from PIL import Image

from studio.artifact_validation import validate_project
from studio.prompt_contract import prompt_contract_for_version
from studio.workflow_builder import build_workflow_package
from studio.workflow_package import read_archive
from tests.contracts.test_story_package_v500 import (
    _stage2_files as _legacy_stage2_files,
)


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 32), "blue").save(stream, format="PNG")
    return stream.getvalue()


def _stage1_files(*, checks: bool = True) -> dict[str, bytes]:
    zones = ("GREETING", "OPENING", "INTRODUCTION", "DEVELOPMENT", "CLIMAX", "FALLING", "ENDING", "FAREWELL")
    story = {
        "schema_version": "4.1.3",
        "meta": {"title": "Cánh cửa", "series": None, "episode": 1, "author": "Katarina",
                 "channel": "Dạ Khúc Trưởng Thành", "profile": "ADULT_STANDARD", "age_band": "18+",
                 "language": "vi", "genre": "Đời sống", "tone": "Ấm áp", "target_minutes": 1,
                 "estimated_minutes": 1, "timing_method": "WHITESPACE_RATE_V1", "tags": ["đời sống"]},
        "characters": [{"character_id": "c001", "name": "An", "age": 30, "role": "Nhân vật chính",
                        "appearance": "Tóc đen, áo xanh", "personality": "Điềm tĩnh", "voice_note": "Giọng trung"}],
        "outline": [{"scene_id": "sc001", "summary": "An mở cửa", "change": "An quyết định bước ra",
                     "setup_or_payoff": "Cánh cửa"}],
        "script": [{"id": f"s{i:04d}", "zone": zone, "scene_id": "sc001", "speaker": "narrator",
                    "text": f"Đoạn kể thứ {i}.", "emotion": "bình tĩnh", "speed": 1.0,
                    "pause_ms": 100, "ambience": None} for i, zone in enumerate(zones, 1)],
    }
    story_raw = _raw(story)
    names = ("cover", "greeting", "opening", "introduction", "development", "climax", "falling", "ending", "farewell", "outro")
    image_prompts = {
        "image_prompt_version": "1.1", "prompt_version": "5.2.0",
        "source_story": {"schema_version": "4.1.3", "sha256": hashlib.sha256(story_raw).hexdigest()},
        "image_mode": "ZONE",
        "prompt_encoding": {"standard": "T5-512", "tokenizer_id": "google/t5-v1_1-xxl",
                            "max_tokens": 512, "count_scope": "RESOLVED_IMAGE_PROMPT",
                            "overflow_policy": "REWRITE"},
        "style_lock": "Minh họa điện ảnh nhất quán.",
        "characters_prompt": "An có tóc đen và mặc áo xanh.",
        "character_locks": [{"character_id": "c001", "description_lock": "Tóc đen, áo xanh.",
                             "planned_reference_path": "characters/c001.png"}],
        "assets": [{"asset_id": name, "basename": f"{name}.png", "role": name.upper(),
                    "source_script_ids": ["s0001"], "character_ids": ["c001"],
                    "brief": f"Khoảnh khắc {name}", "landscape_prompt": f"Ảnh ngang {name}",
                    "portrait_prompt": f"Ảnh dọc {name}", "must_show": [], "must_avoid": []}
                   for name in names],
        "limitations": [],
    }
    clips = []
    for index, row in enumerate(story["script"], 1):
        text = row["text"]
        clips.append({"clip_id": f"clip_{index:04d}",
                      "source_spans": [{"script_id": row["id"], "start_char": 0, "end_char": len(text)}],
                      "estimated_seconds": 2.0, "aspect_ratio": "16:9", "reference_paths": [],
                      "prompt": f"Cảnh {index}", "narration": text, "audio_note": "", "transition": "CUT"})
    video_prompts = {"schema_version": "4.1.3", "source_mode": "STORY_ONLY", "target_model": None,
                     "coverage": "FULL_STORY", "timing_basis": "ESTIMATED",
                     "timing_config": {"method_id": "WHITESPACE_RATE_V1", "rate_per_minute": 200,
                                       "evidence_locator": None},
                     "clips": clips, "limitations": []}
    gate_ids = {
        "JSON_PARSE", "SCHEMA_LINKS", "FILE_SET", "MANIFEST_MATCH", "CONTENT_SAFETY",
        "STORY_NOVELTY", "STORY_ORDER", "STORY_TIMING", "STORY_COMPLETENESS", "STORY_CRAFT",
        "SERIAL_CONTINUITY", "IMAGE_PROMPT_SCHEMA", "IMAGE_PROMPT_SOURCE_BINDING",
        "IMAGE_PROMPT_CHARACTER_LINKS", "IMAGE_PROMPT_T5_TOKENS",
        "IMAGE_REFERENCE_FILES", "IMAGE_REFERENCE_CONTENT",
        "VIDEO_SPANS", "VIDEO_FEASIBILITY", "VIDEO_TIMING",
    }
    review = {"CONTENT_SAFETY", "STORY_NOVELTY", "STORY_COMPLETENESS", "STORY_CRAFT",
              "IMAGE_REFERENCE_CONTENT", "VIDEO_FEASIBILITY"}
    records = [{"id": identifier,
                "status": "NOT_APPLICABLE" if identifier == "SERIAL_CONTINUITY" else "PASS",
                "method": ("MODEL_REVIEW" if identifier in review else
                           "TOOL" if identifier == "IMAGE_PROMPT_T5_TOKENS" else "CODE"),
                "required": True,
                "target": "package", "details": "Đã kiểm trên snapshot hiện tại."}
               for identifier in sorted(gate_ids)] if checks else []
    report = {"schema_version": "5.0.0", "prompt_version": "5.2.0", "stage": 1,
              "status": "COMPLETE", "input_sources": ["Prompt v5.2.0"], "checks": records,
              "limitations": [], "remaining_work": [],
              "archive_validation": {"status": "NOT_CHECKED", "details": "Kiểm sau khi đóng ZIP."}}
    return {"story.json": story_raw, "image_prompts.json": _raw(image_prompts),
            "video_prompts.json": _raw(video_prompts), "validation_report.json": _raw(report),
            "characters/c001.png": _png()}


def test_v520_complete_stage1_passes_full_contract() -> None:
    _payload, result = build_workflow_package(
        1, "CREATE", _stage1_files(), contract=prompt_contract_for_version("5.2.0"),
    )
    assert result["overall_status"] == "PASS"
    assert result["publish_status"] == "PASS"


def test_v520_uses_image_prompt_v11_t5_512_contract() -> None:
    contract = prompt_contract_for_version("5.2.0")
    image = json.loads(_stage1_files()["image_prompts.json"])
    assert contract.image_prompt_version == "1.1"
    assert image["characters_prompt"]
    assert image["prompt_encoding"] == {
        "standard": "T5-512",
        "tokenizer_id": "google/t5-v1_1-xxl",
        "max_tokens": 512,
        "count_scope": "RESOLVED_IMAGE_PROMPT",
        "overflow_policy": "REWRITE",
    }


@pytest.mark.parametrize("missing", ["characters_prompt", "prompt_encoding"])
def test_v520_rejects_missing_t5_512_schema_fields(missing: str) -> None:
    files = _stage1_files()
    image = json.loads(files["image_prompts.json"])
    image.pop(missing)
    files["image_prompts.json"] = _raw(image)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(
            1, "CREATE", files, contract=prompt_contract_for_version("5.2.0"),
        )


def test_v520_t5_token_gate_requires_tool_method() -> None:
    files = _stage1_files()
    report = json.loads(files["validation_report.json"])
    gate = next(row for row in report["checks"] if row["id"] == "IMAGE_PROMPT_T5_TOKENS")
    gate["method"] = "CODE"
    files["validation_report.json"] = _raw(report)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(
            1, "CREATE", files, contract=prompt_contract_for_version("5.2.0"),
        )


def test_v520_complete_stage1_rejects_missing_required_gates() -> None:
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(
            1, "CREATE", _stage1_files(checks=False), contract=prompt_contract_for_version("5.2.0"),
        )


@pytest.mark.parametrize("mutation", ["required_false", "not_applicable", "wrong_method"])
def test_v520_required_gate_policy_cannot_be_bypassed(mutation: str) -> None:
    files = _stage1_files()
    report = json.loads(files["validation_report.json"])
    for row in report["checks"]:
        if mutation == "required_false":
            row["required"] = False
        elif mutation == "not_applicable":
            row["status"] = "NOT_APPLICABLE"
        else:
            row["method"] = "MODEL_REVIEW"
    files["validation_report.json"] = _raw(report)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(1, "CREATE", files, contract=prompt_contract_for_version("5.2.0"))


def test_v520_zip_report_cannot_claim_postzip_pass() -> None:
    files = _stage1_files()
    report = json.loads(files["validation_report.json"])
    report["archive_validation"]["status"] = "PASS"
    files["validation_report.json"] = _raw(report)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(1, "CREATE", files, contract=prompt_contract_for_version("5.2.0"))


def test_v520_rejects_cross_version_image_prompts() -> None:
    files = _stage1_files()
    image = json.loads(files["image_prompts.json"])
    image["prompt_version"] = "5.0.0"
    files["image_prompts.json"] = _raw(image)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(1, "CREATE", files, contract=prompt_contract_for_version("5.2.0"))


def test_v520_stage1_rejects_missing_planned_character_reference() -> None:
    files = _stage1_files()
    files.pop("characters/c001.png")
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(1, "CREATE", files, contract=prompt_contract_for_version("5.2.0"))


def test_v520_rejects_asset_character_without_lock() -> None:
    files = _stage1_files()
    image = json.loads(files["image_prompts.json"])
    image["character_locks"] = []
    files["image_prompts.json"] = _raw(image)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(1, "CREATE", files, contract=prompt_contract_for_version("5.2.0"))


def test_v520_rejects_mixed_reference_mode() -> None:
    files = _stage1_files()
    story = json.loads(files["story.json"])
    story["characters"].append({"character_id": "c002", "name": "Bình", "age": 31,
                                "role": "Cộng sự", "appearance": "Tóc ngắn", "personality": "Nhanh nhẹn",
                                "voice_note": "Giọng sáng"})
    files["story.json"] = _raw(story)
    image = json.loads(files["image_prompts.json"])
    image["source_story"]["sha256"] = hashlib.sha256(files["story.json"]).hexdigest()
    image["character_locks"].append({"character_id": "c002", "description_lock": "Tóc ngắn.",
                                     "planned_reference_path": None})
    image["assets"][0]["character_ids"].append("c002")
    files["image_prompts.json"] = _raw(image)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(1, "CREATE", files, contract=prompt_contract_for_version("5.2.0"))


def test_v520_directory_and_zip_use_the_same_inspector(tmp_path) -> None:
    payload, _result = build_workflow_package(
        1, "CREATE", _stage1_files(), contract=prompt_contract_for_version("5.2.0"),
    )
    archive = tmp_path / "story_stage1.zip"
    archive.write_bytes(payload)
    directory = tmp_path / "extracted"
    directory.mkdir()
    for name, raw in read_archive(payload).items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    zip_result = validate_project(archive)[0]
    directory_result = validate_project(directory)[0]
    assert zip_result.status == directory_result.status == "PASS"
    assert zip_result.checks == directory_result.checks


def test_v520_stage2_rejects_missing_visual_character_binding() -> None:
    contract = prompt_contract_for_version("5.2.0")
    stage1_payload, _ = build_workflow_package(1, "CREATE", _stage1_files(), contract=contract)
    stage1 = read_archive(stage1_payload)
    files = _legacy_stage2_files(stage1)
    plan = json.loads(files["visual_plan.json"])
    plan["reference_mode"] = "IMAGE_REFERENCE"
    plan["characters"] = []
    files["visual_plan.json"] = _raw(plan)
    report = json.loads(files["validation_report.json"])
    report["prompt_version"] = "5.2.0"
    gate_ids = {"JSON_PARSE", "SCHEMA_LINKS", "FILE_SET", "MANIFEST_MATCH", "CONTENT_SAFETY",
                "INHERITED_BYTES", "VISUAL_PLAN", "IMAGE_FILES", "IMAGE_CONTENT"}
    report["checks"] = [{"id": identifier, "status": "PASS",
                         "method": "MODEL_REVIEW" if identifier in {"CONTENT_SAFETY", "IMAGE_CONTENT"} else "CODE",
                         "required": True, "target": "package", "details": "Đã kiểm snapshot."}
                        for identifier in sorted(gate_ids)]
    report["input_sources"] = ["Stage 1 v5.2.0"]
    report["archive_validation"] = {"status": "NOT_CHECKED", "details": "Kiểm sau đóng ZIP."}
    files["validation_report.json"] = _raw(report)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(2, "CREATE", files, parent=stage1, contract=contract)


@pytest.mark.parametrize("mutation", ["extra_field", "bad_reference_mode", "bad_reference_status"])
def test_v520_stage2_rejects_invalid_visual_plan_schema(mutation: str) -> None:
    contract = prompt_contract_for_version("5.2.0")
    stage1_payload, _ = build_workflow_package(1, "CREATE", _stage1_files(), contract=contract)
    stage1 = read_archive(stage1_payload)
    files = _legacy_stage2_files(stage1)
    plan = json.loads(files["visual_plan.json"])
    plan["reference_mode"] = "IMAGE_REFERENCE"
    plan["characters"][0].update({
        "planned_reference_path": "characters/c001.png",
        "reference_path": "characters/c001.png",
        "reference_status": "READY",
    })
    if mutation == "extra_field":
        plan["unexpected"] = True
    elif mutation == "bad_reference_mode":
        plan["reference_mode"] = "DESCRIPTION_ONLY"
    else:
        plan["characters"][0]["reference_status"] = "NOT_APPLICABLE"
    files["visual_plan.json"] = _raw(plan)
    report = json.loads(files["validation_report.json"])
    report["prompt_version"] = "5.2.0"
    gate_ids = {"JSON_PARSE", "SCHEMA_LINKS", "FILE_SET", "MANIFEST_MATCH", "CONTENT_SAFETY",
                "INHERITED_BYTES", "VISUAL_PLAN", "IMAGE_FILES", "IMAGE_CONTENT"}
    report["checks"] = [{"id": identifier, "status": "PASS",
                         "method": "MODEL_REVIEW" if identifier in {"CONTENT_SAFETY", "IMAGE_CONTENT"} else "CODE",
                         "required": True, "target": "package", "details": "Đã kiểm snapshot."}
                        for identifier in sorted(gate_ids)]
    report["input_sources"] = ["Stage 1 v5.2.0"]
    report["archive_validation"] = {"status": "NOT_CHECKED", "details": "Kiểm sau đóng ZIP."}
    files["validation_report.json"] = _raw(report)
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(2, "CREATE", files, parent=stage1, contract=contract)
