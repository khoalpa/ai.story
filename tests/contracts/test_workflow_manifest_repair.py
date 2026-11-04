from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from studio.workflow_builder import (
    build_workflow_package,
    manifest_digest_mismatches,
    plan_directory_integrity_repair,
    repair_directory_integrity,
    repair_directory_manifest,
    restore_integrity_backup,
)
from studio.workflow_package import inspect_directory, read_archive


def _write_package(root: Path) -> None:
    story = {"schema_version": "4.1.3", "meta": {}, "characters": [], "outline": [], "script": []}
    report = {
        "schema_version": "4.1.3", "prompt_version": "4.1.6", "stage": 1, "status": "COMPLETE",
        "input_sources": [], "checks": [], "limitations": [], "remaining_work": [], "archive_validation": {},
    }
    files = {
        "story.json": json.dumps(story).encode(),
        "validation_report.json": json.dumps(report).encode(),
    }
    payload, _result = build_workflow_package(1, "CREATE", files)
    for name, raw in read_archive(payload).items():
        (root / name).write_bytes(raw)


def test_repair_directory_manifest_rebinds_changed_payload_and_checkpoint(tmp_path: Path) -> None:
    _write_package(tmp_path)
    story_path = tmp_path / "story.json"
    story_path.write_bytes(story_path.read_bytes() + b" ")

    differences = manifest_digest_mismatches(tmp_path)
    assert [row["path"] for row in differences] == ["story.json"]
    assert inspect_directory(tmp_path)["status"] == "FAIL"

    result = repair_directory_manifest(tmp_path)

    assert result["status"] == "PASS"
    assert inspect_directory(tmp_path)["status"] == "PASS"
    assert manifest_digest_mismatches(tmp_path) == []
    archive = read_archive(tmp_path / "story_stage1.zip")
    assert archive["story.json"] == story_path.read_bytes()


def test_integrity_repair_previews_backs_up_and_can_undo(tmp_path: Path) -> None:
    _write_package(tmp_path)
    original_manifest = (tmp_path / "manifest.json").read_bytes()
    story_path = tmp_path / "story.json"
    story_path.write_bytes(story_path.read_bytes() + b" ")

    plan = plan_directory_integrity_repair(tmp_path)
    assert plan["can_repair"] is True
    assert [row["kind"] for row in plan["actions"]] == ["REFRESH_DIGESTS"]

    result, backup = repair_directory_integrity(tmp_path)

    assert result["status"] == "PASS"
    assert backup.is_dir()
    assert (backup / "manifest.json").read_bytes() == original_manifest
    assert inspect_directory(tmp_path)["status"] == "PASS"

    restore_integrity_backup(tmp_path, backup)
    assert (tmp_path / "manifest.json").read_bytes() == original_manifest
    assert inspect_directory(tmp_path)["status"] == "FAIL"


def test_integrity_repair_links_manifested_character_image(tmp_path: Path) -> None:
    image = BytesIO()
    Image.new("RGB", (16, 9), "blue").save(image, format="PNG")
    image_raw = image.getvalue()
    stems = (
        "cover", "greeting", "opening", "introduction", "development",
        "climax", "falling", "ending", "farewell", "outro",
    )
    story = {
        "schema_version": "4.1.3", "meta": {},
        "characters": [{"character_id": "c001"}], "outline": [], "script": [],
    }
    plan = {
        "schema_version": "4.1.3", "image_mode": "ZONE",
        "reference_mode": "DESCRIPTION_ONLY",
        "targets": {
            "landscape": {"size_policy": "MODEL_DEFAULT", "preferred_aspect_ratio": "16:9", "width": None, "height": None},
            "portrait": {"size_policy": "MODEL_DEFAULT", "preferred_aspect_ratio": "9:16", "width": None, "height": None},
        },
        "characters": [{
            "character_id": "c001", "planned_reference_path": None,
            "reference_path": None, "reference_status": "NOT_APPLICABLE",
            "description_lock": "Mai",
        }],
        "assets": [{
            "basename": f"{stem}.png", "role": stem.upper(),
            "source_script_ids": [], "character_ids": [], "brief": "fixture",
            "landscape_prompt": "fixture", "portrait_prompt": "fixture",
        } for stem in stems],
    }
    report = {
        "schema_version": "4.1.3", "prompt_version": "4.1.6", "stage": 2,
        "status": "COMPLETE", "input_sources": [], "checks": [],
        "limitations": [], "remaining_work": [], "archive_validation": {},
    }
    files = {
        "story.json": json.dumps(story).encode(),
        "visual_plan.json": json.dumps(plan).encode(),
        "visual_bible.txt": b"fixture",
        "validation_report.json": json.dumps(report).encode(),
        **{f"landscape/{stem}.png": image_raw for stem in stems},
    }
    payload, _result = build_workflow_package(2, "CREATE", files)
    for name, raw in read_archive(payload).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "c001.png").write_bytes(image_raw)

    repair_plan = plan_directory_integrity_repair(tmp_path)
    link = next(row for row in repair_plan["actions"] if row["kind"] == "LINK_CHARACTER_REFERENCES")
    assert link["links"] == [{"character_id": "c001", "path": "characters/c001.png"}]

    result, _backup = repair_directory_integrity(tmp_path)

    assert result["status"] == "PASS"
    repaired = json.loads((tmp_path / "visual_plan.json").read_text(encoding="utf-8"))
    assert repaired["reference_mode"] == "IMAGE_REFERENCE"
    assert repaired["characters"][0]["reference_status"] == "READY"
    assert repaired["characters"][0]["reference_path"] == "characters/c001.png"
