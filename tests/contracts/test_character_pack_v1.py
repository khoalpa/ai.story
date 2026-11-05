from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from studio.character_pack import (
    build_character_pack,
    inspect_character_pack,
    link_character_pack_to_stage1,
    link_character_pack_to_stage2,
    read_character_pack,
)
from studio.prompt_contract import prompt_contract_for_version
from studio.workflow_builder import build_workflow_package
from studio.workflow_package import read_archive
from tests.contracts.test_story_package_v520 import _stage1_files


def _png(color: str) -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 48), color).save(stream, format="PNG")
    return stream.getvalue()


def _documents(*, complete: bool = True):
    images = {}
    views = {}
    for view in ("FRONT", "SIDE", "BACK", "EXPRESSIONS"):
        path = f"characters/c001/{view.casefold()}.png"
        ready = complete or view != "EXPRESSIONS"
        views[view] = {"planned_path": path, "path": path if ready else None, "status": "READY" if ready else "FAILED"}
        if ready:
            images[path] = _png({"FRONT": "red", "SIDE": "green", "BACK": "blue", "EXPRESSIONS": "yellow"}[view])
    pack = {
        "character_pack_version": "1.0", "prompt_version": "4.2.0",
        "source": {"kind": "USER_BRIEF", "identifier": "brief.txt", "sha256": None},
        "style_lock": "Minh họa thiếu nhi, nền trong suốt.",
        "characters": [{"source_character_id": "c001", "safe_id": "c001", "name": "An",
                        "character_lock": "Tóc đen, áo đỏ.", "images": views}],
    }
    status = "COMPLETE" if complete else "PARTIAL"
    report = {
        "character_pack_version": "1.0", "prompt_version": "4.2.0", "scope": "CHARACTER_IMAGE_PACK",
        "status": status, "input_sources": ["brief.txt"], "checks": [], "limitations": [],
        "remaining_work": [] if complete else ["Tạo lại EXPRESSIONS."],
        "archive_validation": {"status": "NOT_CHECKED", "details": "Kiểm sau khi đóng gói"},
    }
    return pack, images, report


def test_complete_character_pack_round_trips() -> None:
    pack, images, report = _documents()
    payload, result = build_character_pack(pack, "Phong cách nhất quán.", images, report)
    assert result["status"] == "PASS"
    reopened = read_character_pack(payload)
    assert inspect_character_pack(reopened, archive=True)["status"] == "PASS"
    assert len([name for name in reopened if name.endswith(".png")]) == 4


def test_partial_pack_does_not_create_placeholder() -> None:
    pack, images, report = _documents(complete=False)
    payload, result = build_character_pack(pack, "Phong cách nhất quán.", images, report)
    assert result["status"] == "PASS"
    assert "characters/c001/expressions.png" not in read_character_pack(payload)


def test_character_pack_metadata_accepts_v500_prompt() -> None:
    pack, images, report = _documents()
    pack["prompt_version"] = "5.0.0"
    report["prompt_version"] = "5.0.0"
    payload, result = build_character_pack(pack, "Phong cách nhất quán.", images, report)
    assert result["status"] == "PASS"
    assert result["manifest"]["prompt_version"] == "5.0.0"
    assert read_character_pack(payload)["character_pack.json"]


def test_complete_pack_rejects_missing_view() -> None:
    pack, images, report = _documents()
    images.pop("characters/c001/back.png")
    with pytest.raises(ValueError, match="Character Image Pack không hợp lệ"):
        build_character_pack(pack, "Phong cách nhất quán.", images, report)


def test_link_front_creates_partial_v420_stage2_repair(sample_archives_dir: Path) -> None:
    contract = prompt_contract_for_version("4.2.0")
    legacy = read_archive(sample_archives_dir / "story_stage2.zip")
    files = {name: raw for name, raw in legacy.items() if name != "manifest.json"}
    stage_report = json.loads(files["validation_report.json"])
    stage_report["prompt_version"] = "4.2.0"
    files["validation_report.json"] = json.dumps(stage_report, ensure_ascii=False, separators=(",", ":")).encode()
    stage2_payload, _ = build_workflow_package(2, "CREATE", files, contract=contract)

    plan = json.loads(files["visual_plan.json"])
    character_id = plan["characters"][0]["character_id"]
    pack, images, pack_report = _documents()
    pack["characters"][0]["source_character_id"] = character_id
    cip_payload, _ = build_character_pack(pack, "Phong cách nhất quán.", images, pack_report)

    repaired, result = link_character_pack_to_stage2(
        stage2_payload, cip_payload, {character_id: character_id}, contract=contract,
    )
    repaired_members = read_archive(repaired)
    repaired_report = json.loads(repaired_members["validation_report.json"])
    repaired_plan = json.loads(repaired_members["visual_plan.json"])
    linked = next(row for row in repaired_plan["characters"] if row["character_id"] == character_id)
    assert result["status"] == "PASS"
    assert result["linked_character_ids"] == [character_id]
    assert repaired_report["status"] == "PARTIAL"
    assert linked["reference_status"] == "READY"
    assert repaired_members[f"characters/{character_id}.png"] == images["characters/c001/front.png"]


def test_link_front_creates_partial_v520_stage1_repair() -> None:
    contract = prompt_contract_for_version("5.2.0")
    stage1_payload, _ = build_workflow_package(1, "CREATE", _stage1_files(), contract=contract)
    pack, images, report = _documents()
    pack["prompt_version"] = report["prompt_version"] = "5.2.0"
    cip_payload, _ = build_character_pack(pack, "Phong cách nhất quán.", images, report)

    repaired, result = link_character_pack_to_stage1(
        stage1_payload, cip_payload, {"c001": "c001"}, contract=contract,
    )

    members = read_archive(repaired)
    repaired_report = json.loads(members["validation_report.json"])
    manifest = json.loads(members["manifest.json"])
    reference_row = next(row for row in manifest["files"] if row["path"] == "characters/c001.png")
    assert result["status"] == "PASS"
    assert repaired_report["status"] == "PARTIAL"
    assert reference_row["origin_stage"] == 1
    assert members["characters/c001.png"] == images["characters/c001/front.png"]


def test_v520_rejects_legacy_stage2_linker(sample_archives_dir: Path) -> None:
    contract = prompt_contract_for_version("5.2.0")
    with pytest.raises(ValueError, match="repair Stage 1"):
        link_character_pack_to_stage2(
            read_archive(sample_archives_dir / "story_stage2.zip"), {}, {}, contract=contract,
        )
