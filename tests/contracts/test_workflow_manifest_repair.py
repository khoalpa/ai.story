from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from studio.prompt_contract import prompt_contract_for_version
from studio.workflow_builder import (
    build_workflow_package,
    manifest_digest_mismatches,
    plan_directory_integrity_repair,
    plan_stage_completion,
    repair_directory_integrity,
    repair_directory_manifest,
    resolve_remaining_work_atomic,
    restore_integrity_backup,
    review_model_gate_atomic,
    scaffold_missing_stage_gates_atomic,
)
from studio.workflow_package import inspect_directory, read_archive
from tests.contracts.test_story_package_v520 import _stage1_files


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


def test_integrity_repair_normalizes_extension_only_visual_basenames(tmp_path: Path) -> None:
    landscape_image = BytesIO()
    portrait_image = BytesIO()
    Image.new("RGB", (16, 9), "blue").save(landscape_image, format="PNG")
    Image.new("RGB", (9, 16), "blue").save(portrait_image, format="PNG")
    landscape_raw = landscape_image.getvalue()
    portrait_raw = portrait_image.getvalue()
    stems = (
        "cover", "greeting", "opening", "introduction", "development",
        "climax", "falling", "ending", "farewell", "outro",
    )
    story = {"schema_version": "4.1.3", "meta": {}, "characters": [], "outline": [], "script": []}
    plan = {
        "schema_version": "4.1.3", "image_mode": "ZONE", "reference_mode": "DESCRIPTION_ONLY",
        "targets": {
            "landscape": {"size_policy": "MODEL_DEFAULT", "preferred_aspect_ratio": "16:9", "width": None, "height": None},
            "portrait": {"size_policy": "MODEL_DEFAULT", "preferred_aspect_ratio": "9:16", "width": None, "height": None},
        },
        "characters": [],
        "assets": [{
            "basename": f"{stem}.png", "role": stem.upper(), "source_script_ids": [],
            "character_ids": [], "brief": "fixture", "landscape_prompt": "fixture", "portrait_prompt": "fixture",
        } for stem in stems],
    }
    report = {
        "schema_version": "4.1.3", "prompt_version": "4.1.6", "stage": 3, "status": "COMPLETE",
        "input_sources": [], "checks": [], "limitations": [], "remaining_work": [], "archive_validation": {},
    }
    files = {
        "story.json": json.dumps(story).encode(),
        "visual_plan.json": json.dumps(plan).encode(),
        "visual_bible.txt": b"fixture",
        "validation_report.json": json.dumps(report).encode(),
        **{f"landscape/{stem}.png": landscape_raw for stem in stems},
        **{f"portrait/{stem}.png": portrait_raw for stem in stems},
    }
    payload, _ = build_workflow_package(3, "CREATE", files)
    for name, raw in read_archive(payload).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    broken = dict(plan)
    broken["assets"] = [{**row, "basename": row["basename"].removesuffix(".png")} for row in plan["assets"]]
    broken_raw = json.dumps(broken).encode()
    (tmp_path / "visual_plan.json").write_bytes(broken_raw)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    visual_row = next(row for row in manifest["files"] if row["path"] == "visual_plan.json")
    visual_row.update(size_bytes=len(broken_raw), sha256=hashlib.sha256(broken_raw).hexdigest())
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    failed = inspect_directory(tmp_path)
    assert failed["integrity_status"] == "FAIL"
    assert {row["check"] for row in failed["checks"] if row["status"] == "FAIL"} == {"file_set", "image_files"}

    repair_plan = plan_directory_integrity_repair(tmp_path)
    normalize = next(row for row in repair_plan["actions"] if row["kind"] == "NORMALIZE_VISUAL_BASENAMES")
    assert repair_plan["can_repair"] is True
    assert len(normalize["changes"]) == 10

    result, backup = repair_directory_integrity(tmp_path)

    assert result["integrity_status"] == "PASS"
    assert inspect_directory(tmp_path)["integrity_status"] == "PASS"
    repaired = json.loads((tmp_path / "visual_plan.json").read_text(encoding="utf-8"))
    assert [row["basename"] for row in repaired["assets"]] == [f"{stem}.png" for stem in stems]
    assert (backup / "visual_plan.json").read_bytes() == broken_raw


def test_basename_repair_refuses_missing_corresponding_image(tmp_path: Path) -> None:
    test_integrity_repair_normalizes_extension_only_visual_basenames(tmp_path)
    # Start from the restored broken snapshot, then remove an image that would
    # be required to prove the extension-only mapping.
    backup = max((tmp_path / ".ai_story_backups").iterdir())
    restore_integrity_backup(tmp_path, backup)
    (tmp_path / "portrait/cover.png").unlink()

    plan = plan_directory_integrity_repair(tmp_path)

    assert not any(row["kind"] == "NORMALIZE_VISUAL_BASENAMES" for row in plan["actions"])
    assert plan["can_repair"] is False


def test_integrity_repair_excludes_unbound_character_from_package_but_keeps_file(tmp_path: Path) -> None:
    test_integrity_repair_normalizes_extension_only_visual_basenames(tmp_path)
    extra_path = tmp_path / "characters/c999.png"
    extra_path.parent.mkdir(exist_ok=True)
    extra_path.write_bytes(b"supplemental")
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append({
        "path": "characters/c999.png", "size_bytes": len(b"supplemental"),
        "sha256": hashlib.sha256(b"supplemental").hexdigest(), "origin_stage": 2,
    })
    manifest["files"] = sorted(manifest["files"], key=lambda row: row["path"])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    plan = plan_directory_integrity_repair(tmp_path)
    exclusion = next(row for row in plan["actions"] if row["kind"] == "EXCLUDE_UNBOUND_CHARACTER_FILES")
    assert exclusion["paths"] == ["characters/c999.png"]
    assert plan["can_repair"] is True

    result, _ = repair_directory_integrity(tmp_path)

    assert result["integrity_status"] == "PASS"
    assert extra_path.read_bytes() == b"supplemental"
    repaired_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "characters/c999.png" not in {row["path"] for row in repaired_manifest["files"]}
    checkpoint = read_archive(tmp_path / "story.zip")
    assert "characters/c999.png" not in checkpoint


def _write_manual_review_package(root: Path) -> None:
    story = {"schema_version": "4.1.3", "meta": {}, "characters": [], "outline": [], "script": []}
    report = {
        "schema_version": "4.1.3", "prompt_version": "4.1.6", "stage": 1, "status": "PARTIAL",
        "input_sources": [],
        "checks": [
            {"id": "IMAGE_CONTENT", "status": "NOT_CHECKED", "method": "MODEL_REVIEW", "required": True,
             "target": "landscape/cover.png", "details": "Cần xem ảnh thật."},
            {"id": "FILE_SET", "status": "PASS", "method": "CODE", "required": True,
             "target": "ZIP root", "details": "Đã kiểm bằng code."},
        ],
        "limitations": [], "remaining_work": [], "archive_validation": {},
    }
    payload, _ = build_workflow_package(1, "CREATE", {
        "story.json": json.dumps(story).encode(),
        "validation_report.json": json.dumps(report).encode(),
    })
    for name, raw in read_archive(payload).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def test_manual_model_gate_review_updates_report_manifest_and_checkpoint(tmp_path: Path) -> None:
    _write_manual_review_package(tmp_path)

    result, backup = review_model_gate_atomic(
        tmp_path, "IMAGE_CONTENT", "PASS",
        "Đã xem trực tiếp cover; nhân dạng, trang phục và hành động khớp visual plan.",
        reviewer="QA nội bộ",
    )

    assert result["integrity_status"] == "PASS"
    report_raw = (tmp_path / "validation_report.json").read_bytes()
    report = json.loads(report_raw)
    gate = next(row for row in report["checks"] if row["id"] == "IMAGE_CONTENT")
    assert gate["status"] == "PASS"
    assert "MANUAL_REVIEW" in gate["details"]
    assert "reviewer=QA nội bộ" in gate["details"]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    row = next(row for row in manifest["files"] if row["path"] == "validation_report.json")
    assert row["size_bytes"] == len(report_raw)
    assert row["sha256"] == hashlib.sha256(report_raw).hexdigest()
    assert read_archive(tmp_path / "story_stage1.zip")["validation_report.json"] == report_raw
    assert (backup / "validation_report.json").is_file()


def test_scaffold_missing_contract_gate_is_atomic_and_does_not_copy_legacy_pass(tmp_path: Path) -> None:
    payload, _ = build_workflow_package(
        1, "CREATE", _stage1_files(), contract=prompt_contract_for_version("5.2.0"),
    )
    members = read_archive(payload)
    report = json.loads(members["validation_report.json"])
    report["checks"] = [row for row in report["checks"] if row["id"] != "JSON_PARSE"]
    report["checks"].append({
        "id": "LEGACY_JSON_PARSE", "status": "PASS", "method": "CODE", "required": True,
        "target": "*.json", "details": "Kết quả từ bộ kiểm cũ.",
    })
    report["status"] = "PARTIAL"
    report_raw = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode()
    manifest = json.loads(members["manifest.json"])
    manifest["status"] = "PARTIAL"
    row = next(item for item in manifest["files"] if item["path"] == "validation_report.json")
    row.update(size_bytes=len(report_raw), sha256=hashlib.sha256(report_raw).hexdigest())
    members["validation_report.json"] = report_raw
    members["manifest.json"] = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode()
    for name, raw in members.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (tmp_path / "story_stage1.zip").write_bytes(payload)

    result, backup, added = scaffold_missing_stage_gates_atomic(tmp_path)

    assert result["integrity_status"] == "PASS"
    assert added == ["JSON_PARSE"]
    repaired = json.loads((tmp_path / "validation_report.json").read_bytes())
    new_gate = next(item for item in repaired["checks"] if item["id"] == "JSON_PARSE")
    assert new_gate["status"] == "NOT_CHECKED"
    assert any(item["id"] == "LEGACY_JSON_PARSE" for item in repaired["checks"])
    assert read_archive(tmp_path / "story_stage1.zip")["validation_report.json"] == (tmp_path / "validation_report.json").read_bytes()
    assert (backup / "validation_report.json").is_file()


def test_manual_gate_review_rejects_code_gate_and_weak_evidence(tmp_path: Path) -> None:
    _write_manual_review_package(tmp_path)

    with pytest.raises(ValueError, match="ít nhất 12"):
        review_model_gate_atomic(tmp_path, "IMAGE_CONTENT", "PASS", "đã xem", reviewer="QA")
    with pytest.raises(ValueError, match="MODEL_REVIEW"):
        review_model_gate_atomic(
            tmp_path, "FILE_SET", "FAIL", "File set có vấn đề cần xử lý.", reviewer="QA",
        )
    with pytest.raises(ValueError, match="người kiểm định"):
        review_model_gate_atomic(
            tmp_path, "IMAGE_CONTENT", "FAIL", "Ảnh không khớp hành động trong brief.", reviewer="",
        )


def test_stage_completion_plan_blocks_remaining_work(tmp_path: Path) -> None:
    _write_manual_review_package(tmp_path)
    report_path = tmp_path / "validation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["checks"][0]["status"] = "PASS"
    report["remaining_work"] = ["Kiểm tra lại nhận dạng nhân vật trong ảnh cover."]
    report_raw = json.dumps(report, separators=(",", ":")).encode()
    report_path.write_bytes(report_raw)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = next(row for row in manifest["files"] if row["path"] == "validation_report.json")
    row.update(size_bytes=len(report_raw), sha256=hashlib.sha256(report_raw).hexdigest())
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")

    plan = plan_stage_completion(tmp_path)

    assert plan["can_complete"] is False
    assert plan["remaining_work"] == report["remaining_work"]
    assert any("remaining_work" in blocker for blocker in plan["blockers"])


def test_stage_completion_plan_closes_obsolete_migration_rerun_work(migrated_stage3_project: Path) -> None:
    from tests.package_fixtures import replace_json

    root = migrated_stage3_project
    report = json.loads((root / "validation_report.json").read_bytes())
    for check in report["checks"]:
        check["status"] = "PASS"
    report["remaining_work"] = ["Chạy lại toàn bộ gate bắt buộc của prompt v5.2.0."]
    replace_json(root, "validation_report.json", report)

    plan = plan_stage_completion(root)

    assert plan["can_complete"] is True or plan["already_complete"] is True
    assert plan["remaining_work"] == []
    assert plan["auto_resolved_work"] == report["remaining_work"]


def test_resolve_remaining_work_updates_report_manifest_and_checkpoint(tmp_path: Path) -> None:
    _write_manual_review_package(tmp_path)
    report_path = tmp_path / "validation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["checks"][0]["status"] = "PASS"
    work = "Kiểm tra lại nhận dạng nhân vật trong ảnh cover."
    report["remaining_work"] = [work]
    report["limitations"] = ["IMAGE_CONTENT is NOT_CHECKED pending editorial review."]
    report_raw = json.dumps(report, separators=(",", ":")).encode()
    report_path.write_bytes(report_raw)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = next(row for row in manifest["files"] if row["path"] == "validation_report.json")
    row.update(size_bytes=len(report_raw), sha256=hashlib.sha256(report_raw).hexdigest())
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")

    result, backup = resolve_remaining_work_atomic(
        tmp_path, [work], "Đã đối chiếu ảnh cover với khóa nhân vật và xác nhận đạt.", reviewer="QA nội bộ",
    )

    assert result["integrity_status"] == "PASS"
    updated_raw = report_path.read_bytes()
    updated = json.loads(updated_raw)
    assert updated["remaining_work"] == []
    assert updated["limitations"] == []
    assert any("WORK_RESOLUTION" in item for item in updated["input_sources"])
    assert "WORK_RESOLUTION" in updated["checks"][0]["details"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = next(row for row in manifest["files"] if row["path"] == "validation_report.json")
    assert row["sha256"] == hashlib.sha256(updated_raw).hexdigest()
    assert read_archive(tmp_path / "story_stage1.zip")["validation_report.json"] == updated_raw
    assert (backup / "validation_report.json").is_file()
