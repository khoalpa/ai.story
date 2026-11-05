from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from studio.package_migration import (
    migrate_extracted_package,
    publish_migrated_package,
    rebuild_v520_checkpoint_chain,
)
from studio.prompt_contract import prompt_contract_for_version
from studio.reference_samples import load_reference_package
from studio.workflow_builder import (
    build_workflow_package,
    rerun_deterministic_gates_atomic,
)
from studio.workflow_package import inspect_directory, read_archive
from studio.workflow_views import image_prompt_schema_repair_candidate
from tests.contracts.test_story_package_v520 import _stage1_files


def _extracted_v510(root: Path) -> Path:
    files = _stage1_files()
    image = json.loads(files["image_prompts.json"])
    image["prompt_version"] = "5.1.0"
    image["image_prompt_version"] = "1.0"
    image.pop("prompt_encoding")
    image.pop("characters_prompt")
    for row in image["character_locks"]:
        row["planned_reference_path"] = None
    files["image_prompts.json"] = json.dumps(image, ensure_ascii=False, separators=(",", ":")).encode()
    files.pop("characters/c001.png")
    report = json.loads(files["validation_report.json"])
    report["prompt_version"] = "5.1.0"
    report["checks"] = []
    report["input_sources"] = []
    report["archive_validation"] = {}
    files["validation_report.json"] = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode()
    payload, _ = build_workflow_package(1, "CREATE", files, contract=prompt_contract_for_version("5.1.0"))
    root.mkdir()
    for name, raw in read_archive(payload).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return root


def _partially_upgraded_v520(root: Path) -> Path:
    payload, _ = build_workflow_package(
        1, "CREATE", _stage1_files(), contract=prompt_contract_for_version("5.2.0")
    )
    members = read_archive(payload)
    image = json.loads(members["image_prompts.json"])
    image["image_prompt_version"] = "1.0"
    image.pop("prompt_encoding")
    image.pop("characters_prompt")
    image["legacy_metadata"] = {"upgraded": True}
    members["image_prompts.json"] = json.dumps(
        image, ensure_ascii=False, separators=(",", ":")
    ).encode()
    manifest = json.loads(members["manifest.json"])
    row = next(item for item in manifest["files"] if item["path"] == "image_prompts.json")
    row["size_bytes"] = len(members["image_prompts.json"])
    row["sha256"] = hashlib.sha256(members["image_prompts.json"]).hexdigest()
    members["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":")
    ).encode()
    root.mkdir()
    for name, raw in members.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return root


def test_migrates_extracted_v510_without_changing_source(tmp_path: Path) -> None:
    source = _extracted_v510(tmp_path / "source")
    before = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}

    result = migrate_extracted_package(source)

    assert result.source_version == "5.1.0"
    assert result.target_version == "5.2.2"
    assert result.status == "MIGRATED_WITH_WARNINGS"
    assert json.loads(result.members["manifest.json"])["status"] == "PARTIAL"
    assert json.loads(result.members["validation_report.json"])["checks"]
    assert all(row["status"] == "NOT_CHECKED" for row in json.loads(result.members["validation_report.json"])["checks"])
    assert before == {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}


def test_repairs_partially_upgraded_v520_image_prompt_schema(tmp_path: Path) -> None:
    source = _partially_upgraded_v520(tmp_path / "source")

    result = migrate_extracted_package(source)

    image = json.loads(result.members["image_prompts.json"])
    assert set(image) == {
        "image_prompt_version", "prompt_version", "source_story", "image_mode",
        "prompt_encoding", "style_lock", "characters_prompt", "character_locks",
        "assets", "limitations",
    }
    assert image["image_prompt_version"] == "1.1"
    assert image["prompt_version"] == "5.2.2"
    assert image["characters_prompt"]
    assert image["prompt_encoding"]["standard"] == "T5-512"
    assert result.inspection["integrity_status"] == "PASS"


def test_contextual_repair_is_offered_only_for_directory_image_prompt_failure() -> None:
    image_only = {
        "checks": [
            {"check": "manifest_schema", "status": "PASS"},
            {"check": "image_prompts", "status": "FAIL"},
        ],
    }
    assert image_prompt_schema_repair_candidate(image_only)
    assert not image_prompt_schema_repair_candidate({**image_only, "archive": True})
    assert not image_prompt_schema_repair_candidate({
        "checks": image_only["checks"] + [{"check": "file_digest", "status": "FAIL"}],
    })


def test_publishes_to_new_directory_and_rejects_nonempty_destination(tmp_path: Path) -> None:
    result = migrate_extracted_package(_extracted_v510(tmp_path / "source"))
    destination = publish_migrated_package(result, tmp_path / "migrated")
    assert (destination / "migration_report.json").is_file()
    assert (destination / "story_stage1.zip").read_bytes() == result.archive_bytes
    assert inspect_directory(destination)["integrity_status"] == "PASS"
    with pytest.raises(ValueError, match="trống"):
        publish_migrated_package(result, destination)


def test_reruns_locally_provable_code_gates_after_migration(tmp_path: Path) -> None:
    migration = migrate_extracted_package(_extracted_v510(tmp_path / "source"))
    destination = publish_migrated_package(migration, tmp_path / "migrated")

    inspection, _backup, updated = rerun_deterministic_gates_atomic(destination)

    report = json.loads((destination / "validation_report.json").read_bytes())
    statuses = {row["id"]: row["status"] for row in report["checks"]}
    assert {"JSON_PARSE", "SCHEMA_LINKS", "FILE_SET", "MANIFEST_MATCH"} <= set(updated)
    assert statuses["JSON_PARSE"] == "PASS"
    assert statuses["CONTENT_SAFETY"] == "NOT_CHECKED"
    assert statuses["IMAGE_PROMPT_T5_TOKENS"] == "NOT_CHECKED"
    assert inspection["integrity_status"] == "PASS"


def test_rejects_unsupported_and_tampered_sources(tmp_path: Path) -> None:
    source = _extracted_v510(tmp_path / "source")
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["prompt_version"] = "4.2.0"
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="UNSUPPORTED_SOURCE"):
        migrate_extracted_package(source)

    source = _extracted_v510(tmp_path / "source2")
    (source / "story.json").write_bytes((source / "story.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="SOURCE_INVALID"):
        migrate_extracted_package(source)


def test_migrates_extracted_v416_stage4_to_v520_stage3(tmp_path: Path, sample_archives_dir: Path) -> None:
    members, _ = load_reference_package("story_video_prompts.zip", sample_archives_dir)
    source = tmp_path / "legacy"
    source.mkdir()
    for name, raw in members.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    result = migrate_extracted_package(source)

    assert result.source_version == "4.1.6"
    assert result.stage == 3
    assert result.report["source_stage"] == 4
    assert result.report["target_stage"] == 3
    assert "image_prompts.json" in result.members
    assert result.inspection["integrity_status"] == "PASS"


def test_v4_migration_normalizes_ready_references_to_image_reference(sample_stage4_project: Path) -> None:
    from tests.package_fixtures import replace_json

    source = sample_stage4_project
    plan = json.loads((source / "visual_plan.json").read_bytes())
    plan["reference_mode"] = "DESCRIPTION_ONLY"
    for asset in plan["assets"]:
        asset["character_ids"] = ["c001", "c003"]
    replace_json(source, "visual_plan.json", plan)

    result = migrate_extracted_package(source)

    visual = json.loads(result.members["visual_plan.json"])
    prompts = json.loads(result.members["image_prompts.json"])
    assert visual["reference_mode"] == "IMAGE_REFERENCE"
    assert {row["character_id"] for row in visual["characters"]} == {"c001", "c003"}
    assert all(row["reference_status"] == "READY" for row in visual["characters"])
    assert {row["character_id"] for row in prompts["character_locks"]} == {
        "c001", "c002", "c003",
    }
    assert result.inspection["integrity_status"] == "PASS"


def test_rebuilds_v520_stage3_lineage_with_verified_parent_bytes(migrated_stage3_project: Path) -> None:
    source = migrated_stage3_project

    result = rebuild_v520_checkpoint_chain(source)

    assert list(result.archives) == ["story_stage1.zip", "story_stage2.zip", "story.zip"]
    assert result.inspections[2]["integrity_status"] == "PASS"
    assert result.inspections[3]["integrity_status"] == "PASS"
    assert next(
        row for row in result.inspections[3]["checks"]
        if row["check"] == "inherited_bytes"
    )["status"] == "PASS"
