from __future__ import annotations

import hashlib
import json
from pathlib import Path

from studio.image_prompt_validation import ASSET_FIELDS, image_prompt_asset_diagnostics
from studio.prompt_contract import prompt_contract_for_version
from studio.workflow_builder import (
    _sync_image_prompt_dependents,
    build_workflow_package,
    plan_directory_integrity_repair,
    repair_directory_integrity,
)
from studio.workflow_package import read_archive
from tests.contracts.test_prompt_release_v522 import _stage1_files_v522


def _asset(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "asset_id": "cover", "basename": "cover.png", "role": "COVER",
        "source_script_ids": ["S001"], "character_ids": ["C001"],
        "brief": "Cover", "landscape_prompt": "Landscape",
        "portrait_prompt": "Portrait", "must_show": [], "must_avoid": [],
    }
    value.update(updates)
    assert set(value) == ASSET_FIELDS
    return value


def test_asset_diagnostics_identifies_exact_invalid_fields_and_references() -> None:
    story = {
        "characters": [{"character_id": "c001"}],
        "script": [{"id": "s001"}],
    }
    plan = {"assets": [_asset(source_script_ids=["S001", "S001"], character_ids=["C001"])]}

    diagnostics = image_prompt_asset_diagnostics(plan, story)

    assert [(row["field"], row["code"]) for row in diagnostics] == [
        ("source_script_ids", "DUPLICATES"),
        ("source_script_ids", "UNKNOWN_REFERENCES"),
        ("character_ids", "UNKNOWN_REFERENCES"),
    ]
    assert diagnostics[1]["allowed"] == ["s001"]
    assert diagnostics[2]["allowed"] == ["c001"]


def test_asset_diagnostics_reports_schema_and_empty_required_reference() -> None:
    story = {"characters": [], "script": []}
    broken = _asset(source_script_ids=[])
    del broken["brief"]
    broken["unexpected"] = True

    diagnostics = image_prompt_asset_diagnostics({"assets": [broken]}, story)

    assert any(row["code"] == "MISSING_FIELDS" and row["values"] == ["brief"] for row in diagnostics)
    assert any(row["code"] == "EXTRA_FIELDS" and row["values"] == ["unexpected"] for row in diagnostics)
    assert any(row["field"] == "source_script_ids" and row["code"] == "EMPTY_LIST" for row in diagnostics)


def test_guided_repair_resolves_empty_asset_sources_and_keeps_extra_file_on_disk(tmp_path: Path) -> None:
    payload, _ = build_workflow_package(
        1, "CREATE", _stage1_files_v522(), contract=prompt_contract_for_version("5.2.2"),
    )
    for name, raw in read_archive(payload).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    image_path = tmp_path / "image_prompts.json"
    image_prompts = json.loads(image_path.read_text(encoding="utf-8"))
    image_prompts["assets"][0]["source_script_ids"] = []
    image_prompts["assets"][9]["source_script_ids"] = []
    image_raw = json.dumps(image_prompts, ensure_ascii=False, separators=(",", ":")).encode()
    image_path.write_bytes(image_raw)
    readme_raw = b"project notes"
    (tmp_path / "README.txt").write_bytes(readme_raw)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_row = next(row for row in manifest["files"] if row["path"] == "image_prompts.json")
    image_row.update(size_bytes=len(image_raw), sha256=hashlib.sha256(image_raw).hexdigest())
    manifest["files"].append({
        "path": "README.txt", "size_bytes": len(readme_raw),
        "sha256": hashlib.sha256(readme_raw).hexdigest(), "origin_stage": 1,
    })
    manifest["files"] = sorted(manifest["files"], key=lambda row: row["path"])
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")

    initial = plan_directory_integrity_repair(tmp_path)
    assert initial["can_repair"] is False
    assert {row["kind"] for row in initial["decision_requests"]} == {"EXTRA_FILE", "ASSET_SOURCE_IDS"}

    resolutions = {
        "exclude_paths": ["README.txt"],
        "asset_source_ids": {"0": ["s0001"], "9": ["s0008"]},
    }
    resolved = plan_directory_integrity_repair(tmp_path, resolutions=resolutions)
    assert resolved["can_repair"] is True
    result, _backup = repair_directory_integrity(tmp_path, resolutions=resolutions)

    assert result["integrity_status"] == "PASS"
    repaired = json.loads(image_path.read_text(encoding="utf-8"))
    assert repaired["assets"][0]["source_script_ids"] == ["s0001"]
    assert repaired["assets"][9]["source_script_ids"] == ["s0008"]
    report = json.loads((tmp_path / "validation_report.json").read_text(encoding="utf-8"))
    assert report["archive_validation"]["status"] == "NOT_CHECKED"
    affected = {
        row["id"]: row["status"] for row in report["checks"]
        if row["id"] in {"SCHEMA_LINKS", "IMAGE_PROMPT_SCHEMA", "IMAGE_PROMPT_SOURCE_BINDING"}
    }
    assert affected and set(affected.values()) == {"NOT_CHECKED"}
    assert (tmp_path / "README.txt").read_bytes() == readme_raw
    repaired_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "README.txt" not in {row["path"] for row in repaired_manifest["files"]}


def test_asset_repair_synchronizes_visual_projection_and_invalidates_old_evidence() -> None:
    prompt_asset = _asset(source_script_ids=["s0009"])
    visual_asset = {key: value for key, value in prompt_asset.items() if key not in {"asset_id", "must_show", "must_avoid"}}
    visual_asset["source_script_ids"] = []
    files = {
        "image_prompts.json": json.dumps({"assets": [prompt_asset]}).encode(),
        "visual_plan.json": json.dumps({"assets": [visual_asset]}).encode(),
        "validation_report.json": json.dumps({
            "archive_validation": {"status": "PASS", "details": "Archive cũ đã kiểm."},
            "checks": [{"id": "SCHEMA_LINKS", "status": "PASS", "details": "Bằng chứng cũ."}],
        }).encode(),
    }

    changed = _sync_image_prompt_dependents(files)

    visual = json.loads(files["visual_plan.json"])
    assert visual["assets"][0]["source_script_ids"] == ["s0009"]
    report = json.loads(files["validation_report.json"])
    assert report["archive_validation"]["status"] == "NOT_CHECKED"
    assert report["checks"][0]["status"] == "NOT_CHECKED"
    assert set(changed) == {"visual_plan.json", "validation_report.json"}
