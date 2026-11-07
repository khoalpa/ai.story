from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from studio.summary_visual import build_summary_visual_plan
from studio.summary_workflow import (
    complete_summary_stage,
    plan_summary_completion,
    rebuild_summary_manifest,
    repair_summary_manifest,
    revalidate_summary_media,
    summary_manifest_issues,
)
from tests.contracts.test_summary_projection import summary_fixture


def _write_stage1(root: Path, *, validation_status: str = "COMPLETE") -> None:
    (root / "summary.json").write_text("{}", encoding="utf-8")
    (root / "summary_validation_report.json").write_text(json.dumps({
        "status": validation_status,
        "checks": [{"id": "SCHEMA", "status": "PASS"}],
        "remaining_work": [],
    }), encoding="utf-8")
    (root / "summary_stage.json").write_text(json.dumps({
        "schema_version": "1.0.0",
        "prompt_version": "1.5.2",
        "stage": 1,
        "parent_package_sha256": None,
        "status": "PARTIAL",
    }), encoding="utf-8")
    (root / "summary_manifest.json").write_text(json.dumps({
        "schema_version": "1.0.0",
        "prompt_version": "1.5.2",
        "status": "PARTIAL",
        "parent_package_sha256": None,
        "source_fingerprints": [],
        "files": [],
    }), encoding="utf-8")
    (root / "summary_manifest.json").write_bytes(rebuild_summary_manifest(root))


def test_summary_manifest_repair_rebinds_changed_payload_and_keeps_backup(tmp_path: Path) -> None:
    _write_stage1(tmp_path)
    (tmp_path / "summary.json").write_text('{"changed":true}', encoding="utf-8")

    assert summary_manifest_issues(tmp_path) == ["Manifest size/hash không khớp: summary.json"]

    backup = repair_summary_manifest(tmp_path)

    assert backup.is_dir()
    assert (backup / "summary_manifest.json").is_file()
    assert summary_manifest_issues(tmp_path) == []


def test_summary_stage_completion_updates_stage_and_rebinds_manifest(tmp_path: Path) -> None:
    _write_stage1(tmp_path)

    plan = plan_summary_completion(tmp_path)
    assert plan["can_complete"] is True

    backup = complete_summary_stage(tmp_path)

    assert backup.is_dir()
    assert json.loads((tmp_path / "summary_stage.json").read_text(encoding="utf-8"))["status"] == "COMPLETE"
    assert json.loads((tmp_path / "summary_manifest.json").read_text(encoding="utf-8"))["status"] == "COMPLETE"
    assert summary_manifest_issues(tmp_path) == []


def test_summary_stage_completion_is_blocked_by_incomplete_validation(tmp_path: Path) -> None:
    _write_stage1(tmp_path, validation_status="PARTIAL")

    plan = plan_summary_completion(tmp_path)

    assert plan["can_complete"] is False
    assert any("Validation đang là PARTIAL" in blocker for blocker in plan["blockers"])


def test_manifest_repair_restores_media_metadata_from_plan_and_review(tmp_path: Path) -> None:
    _write_stage1(tmp_path)
    stage = json.loads((tmp_path / "summary_stage.json").read_text(encoding="utf-8"))
    stage.update(
        prompt_version="1.5.2",
        stage=3,
        parent_package_sha256="a" * 64,
    )
    (tmp_path / "summary_stage.json").write_text(json.dumps(stage), encoding="utf-8")
    media = tmp_path / "landscape" / "scene_0001.png"
    media.parent.mkdir()
    Image.new("RGB", (16, 9)).save(media)
    (tmp_path / "summary_render_plan.json").write_text(json.dumps({
        "assets": [{
            "asset_id": "asset_0001_landscape",
            "scene_id": "scene_0001",
            "orientation": "landscape",
            "output_path": "landscape/scene_0001.png",
            "required": True,
            "status": "VALIDATED",
        }],
    }), encoding="utf-8")
    (tmp_path / "summary_media_review.json").write_text(json.dumps({
        "assets": [{
            "asset_id": "asset_0001_landscape",
            "scene_id": "scene_0001",
            "path": "landscape/scene_0001.png",
            "checks": {"visual_fact": "PASS", "safety": "PASS"},
            "issues": [],
            "recommended_action": "NONE",
        }],
    }), encoding="utf-8")

    raw = rebuild_summary_manifest(tmp_path)
    manifest = json.loads(raw)
    row = next(item for item in manifest["files"] if item["path"] == "landscape/scene_0001.png")

    assert manifest["prompt_version"] == "1.5.2"
    assert manifest["parent_package_sha256"] == "a" * 64
    assert row["asset_id"] == "asset_0001_landscape"
    assert row["scene_id"] == "scene_0001"
    assert row["origin"] == "STAGE2_LANDSCAPE"
    assert row["review_status"] == "PASS"
    assert (row["width"], row["height"]) == (16, 9)


def test_revalidate_summary_media_rebuilds_complete_stage3_evidence(tmp_path: Path) -> None:
    _write_stage1(tmp_path)
    summary = summary_fixture()
    visual = build_summary_visual_plan(summary)
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "summary_visual_plan.json").write_text(json.dumps(visual), encoding="utf-8")
    stage = json.loads((tmp_path / "summary_stage.json").read_text(encoding="utf-8"))
    stage["stage"] = 3
    stage["parent_package_sha256"] = "a" * 64
    (tmp_path / "summary_stage.json").write_text(json.dumps(stage), encoding="utf-8")
    validation = {
        "status": "PARTIAL",
        "checks": [
            {"id": name, "status": "FAIL" if name == "MEDIA_REVIEW" else "PASS"}
            for name in ("IMAGE_FILES", "MEDIA_REVIEW", "ORIENTATION_PARITY", "MANIFEST_MATCH")
        ],
        "remaining_work": ["review media"],
        "limitations": ["SCENE 0007: old limitation"],
    }
    (tmp_path / "summary_validation_report.json").write_text(json.dumps(validation), encoding="utf-8")
    approved_assets = []
    checks = {
        "visual_fact": "PASS",
        "source_grounding": "PASS",
        "style_continuity": "PASS",
        "entity_continuity": "NOT_APPLICABLE",
        "numeric_fidelity": "NOT_APPLICABLE",
        "text_quality": "NOT_APPLICABLE",
        "safety": "PASS",
    }
    for scene in visual["scenes"]:
        for orientation, size in (("landscape", (16, 9)), ("portrait", (9, 16))):
            path = tmp_path / orientation / f"{scene['scene_id']}.png"
            path.parent.mkdir(exist_ok=True)
            Image.new("RGB", size, color=(len(approved_assets), 10, 20)).save(path)
            approved_assets.append({
                "asset_id": f"{scene['scene_id']}_{orientation}",
                "checks": dict(checks),
            })

    backup = revalidate_summary_media(tmp_path, {
        "schema_version": "1.0.0",
        "assets": approved_assets,
    })

    assert backup.is_dir()
    report = json.loads((tmp_path / "summary_validation_report.json").read_text(encoding="utf-8"))
    plan = json.loads((tmp_path / "summary_render_plan.json").read_text(encoding="utf-8"))
    assert report["status"] == "COMPLETE"
    assert report["remaining_work"] == []
    assert all(row["status"] == "VALIDATED" for row in plan["assets"])
    assert summary_manifest_issues(tmp_path) == []
