from __future__ import annotations

import hashlib
import json
from io import BytesIO

import pytest
from PIL import Image

from studio.prompt_contract import load_prompt_contract, prompt_contract_for_version
from studio.workflow_builder import build_workflow_package
from studio.workflow_package import inspect_members, read_archive
from video.story_package_v416 import load_package_bytes as load_video_package_bytes


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _stage1_files() -> dict[str, bytes]:
    story = {
        "schema_version": "4.1.3",
        "meta": {"profile": "ADULT_STANDARD"},
        "characters": [{"character_id": "c001", "name": "An"}],
        "outline": [{"scene_id": "sc001"}],
        "script": [{"id": "s0001", "text": "An mở cánh cửa."}],
    }
    story_raw = _raw(story)
    names = ("cover", "greeting", "opening", "introduction", "development", "climax", "falling", "ending", "farewell", "outro")
    image_prompts = {
        "image_prompt_version": "1.0", "prompt_version": "5.0.0",
        "source_story": {"schema_version": "4.1.3", "sha256": hashlib.sha256(story_raw).hexdigest()},
        "image_mode": "ZONE", "style_lock": "Minh họa điện ảnh nhất quán.",
        "character_locks": [{"character_id": "c001", "description_lock": "Tóc đen, áo xanh.", "planned_reference_path": "characters/c001.png"}],
        "assets": [{
            "asset_id": name, "basename": f"{name}.png", "role": name.upper(),
            "source_script_ids": ["s0001"], "character_ids": ["c001"],
            "brief": f"Khoảnh khắc {name}", "landscape_prompt": f"Ảnh ngang {name}",
            "portrait_prompt": f"Ảnh dọc {name}", "must_show": [], "must_avoid": [],
        } for name in names],
        "limitations": [],
    }
    text = story["script"][0]["text"]
    video_prompts = {
        "schema_version": "4.1.3", "source_mode": "STORY_ONLY", "target_model": None,
        "coverage": "FULL_STORY", "timing_basis": "ESTIMATED", "timing_config": {},
        "clips": [{
            "clip_id": "clip_0001", "source_spans": [{"script_id": "s0001", "start_char": 0, "end_char": len(text)}],
            "estimated_seconds": 3.0, "aspect_ratio": "16:9", "reference_paths": [],
            "prompt": "An mở cửa", "narration": text, "audio_note": "", "transition": "CUT",
        }],
        "limitations": [],
    }
    report = {
        "schema_version": "5.0.0", "prompt_version": "5.0.0", "stage": 1,
        "status": "COMPLETE", "input_sources": [], "checks": [], "limitations": [],
        "remaining_work": [], "archive_validation": {},
    }
    return {"story.json": story_raw, "image_prompts.json": _raw(image_prompts),
            "video_prompts.json": _raw(video_prompts), "validation_report.json": _raw(report)}


def _png(*, portrait: bool = False) -> bytes:
    stream = BytesIO()
    Image.new("RGB", (24, 40) if portrait else (40, 24), "blue").save(stream, format="PNG")
    return stream.getvalue()


def _next_report(stage: int) -> bytes:
    return _raw({
        "schema_version": "5.0.0", "prompt_version": "5.0.0", "stage": stage,
        "status": "COMPLETE", "input_sources": [], "checks": [], "limitations": [],
        "remaining_work": [], "archive_validation": {},
    })


def _stage2_files(stage1_members: dict[str, bytes]) -> dict[str, bytes]:
    files = {name: raw for name, raw in stage1_members.items() if name != "manifest.json"}
    files["validation_report.json"] = _next_report(2)
    prompts = json.loads(files["image_prompts.json"])
    assets = [{
        "basename": row["basename"], "role": row["role"],
        "source_script_ids": row["source_script_ids"], "character_ids": row["character_ids"],
        "brief": row["brief"], "landscape_prompt": row["landscape_prompt"],
        "portrait_prompt": row["portrait_prompt"],
    } for row in prompts["assets"]]
    files["visual_plan.json"] = _raw({
        "schema_version": "4.1.3", "image_mode": "ZONE", "reference_mode": "DESCRIPTION_ONLY",
        "targets": {
            "landscape": {"size_policy": "MODEL_DEFAULT", "preferred_aspect_ratio": "16:9", "width": None, "height": None},
            "portrait": {"size_policy": "MODEL_DEFAULT", "preferred_aspect_ratio": "9:16", "width": None, "height": None},
        },
        "characters": [{"character_id": "c001", "planned_reference_path": None, "reference_path": None,
                        "reference_status": "NOT_APPLICABLE", "description_lock": "Tóc đen, áo xanh."}],
        "assets": assets,
    })
    files["visual_bible.txt"] = b"consistent style"
    for row in prompts["assets"]:
        files[f"landscape/{row['basename']}"] = _png()
    return files


def test_v522_is_current_three_stage_contract() -> None:
    contract = load_prompt_contract()
    assert contract.version_label == "5.2.2"
    assert contract.workflow_package_stages == ("STAGE1", "STAGE2", "STAGE3")
    assert contract.workflow_manifest_schema_version == "5.0.0"
    assert contract.image_prompt_version == "1.1"


def test_v500_stage1_requires_and_validates_both_prompt_files() -> None:
    payload, result = build_workflow_package(1, "CREATE", _stage1_files())
    assert result["status"] == "PASS"
    reopened = inspect_members(read_archive(payload), archive=True)
    assert reopened["status"] == "PASS"
    assert reopened["stage"] == "STAGE1"
    assert {"image_prompts", "video_prompts"} <= {
        row["check"] for row in reopened["checks"] if row["status"] == "PASS"
    }


def test_v500_rejects_stage4() -> None:
    with pytest.raises(ValueError, match="không hỗ trợ Stage 4"):
        build_workflow_package(4, "CREATE", _stage1_files())


def test_v500_rejects_missing_image_prompts() -> None:
    files = _stage1_files()
    files.pop("image_prompts.json")
    with pytest.raises(ValueError, match="Gói tạo ra không hợp lệ"):
        build_workflow_package(1, "CREATE", files)


def test_v500_stage3_is_final_and_inherits_prompt_bytes() -> None:
    stage1_payload, _ = build_workflow_package(1, "CREATE", _stage1_files())
    stage1 = read_archive(stage1_payload)
    stage2_payload, stage2_result = build_workflow_package(2, "CREATE", _stage2_files(stage1), parent=stage1)
    assert stage2_result["status"] == "PASS"
    stage2 = read_archive(stage2_payload)
    stage3_files = {name: raw for name, raw in stage2.items() if name != "manifest.json"}
    stage3_files["validation_report.json"] = _next_report(3)
    prompts = json.loads(stage3_files["image_prompts.json"])
    for row in prompts["assets"]:
        stage3_files[f"portrait/{row['basename']}"] = _png(portrait=True)
    final_payload, final_result = build_workflow_package(3, "CREATE", stage3_files, parent=stage2)
    final = read_archive(final_payload)
    assert final_result["status"] == "PASS"
    assert final_result["stage"] == "STAGE3"
    assert final["image_prompts.json"] == stage1["image_prompts.json"]
    assert final["video_prompts.json"] == stage1["video_prompts.json"]
    assert "story_video_prompts.zip" not in final


def test_video_reader_accepts_v500_stage2_package() -> None:
    stage1_payload, _ = build_workflow_package(1, "CREATE", _stage1_files())
    stage1 = read_archive(stage1_payload)
    stage2_payload, _ = build_workflow_package(2, "CREATE", _stage2_files(stage1), parent=stage1)
    members, inspection = load_video_package_bytes(stage2_payload)
    assert inspection["stage"] == "STAGE2"
    assert "video_prompts.json" in members


def test_v500_stage2_rejects_changed_inherited_prompt() -> None:
    stage1_payload, _ = build_workflow_package(1, "CREATE", _stage1_files())
    stage1 = read_archive(stage1_payload)
    files = _stage2_files(stage1)
    image_plan = json.loads(files["image_prompts.json"])
    image_plan["style_lock"] = "changed"
    files["image_prompts.json"] = _raw(image_plan)
    with pytest.raises(ValueError, match="Payload kế thừa|exact bytes"):
        build_workflow_package(2, "CREATE", files, parent=stage1)


def test_v4_contracts_remain_four_stage_legacy() -> None:
    for version in ("4.1.6", "4.2.0"):
        assert prompt_contract_for_version(version).workflow_package_stages[-1] == "STAGE4"
