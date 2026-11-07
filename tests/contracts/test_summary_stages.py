from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from studio.summary_audit import audit_summary_package
from studio.summary_cli import stage1_main
from studio.summary_media import REVIEW_CHECKS
from studio.summary_package import canonical_json_bytes
from studio.summary_stages import (
    build_summary_stage1,
    build_summary_stage2,
    build_summary_stage3,
)
from tests.contracts.test_summary_projection import summary_fixture


def _png(color: str, *, portrait: bool = False) -> bytes:
    output = io.BytesIO()
    size = (90, 160) if portrait else (160, 90)
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def _review(*asset_ids: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "assets": [
            {"asset_id": asset_id, "checks": {name: "PASS" for name in REVIEW_CHECKS}}
            for asset_id in asset_ids
        ],
    }


def _json_member(path: Path, name: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read(name))


def _raw_member(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name)


def test_three_stage_summary_pipeline_preserves_lineage(tmp_path: Path) -> None:
    stage1 = build_summary_stage1(summary_fixture(), tmp_path / "summary_stage1.zip")
    assert audit_summary_package(stage1).status == "PASS"
    assert _json_member(stage1, "summary_stage.json")["stage"] == 1
    assert _json_member(stage1, "summary_manifest.json")["status"] == "COMPLETE"

    landscape_root = tmp_path / "stage2_media"
    (landscape_root / "landscape").mkdir(parents=True)
    (landscape_root / "landscape" / "scene_0001.png").write_bytes(_png("navy"))
    stage2 = build_summary_stage2(
        stage1,
        tmp_path / "summary_stage2.zip",
        landscape_root,
        _review("scene_0001_landscape"),
    )
    stage2_meta = _json_member(stage2, "summary_stage.json")
    assert audit_summary_package(stage2).status == "PASS"
    assert stage2_meta["stage"] == 2
    assert (
        stage2_meta["parent_package_sha256"]
        == hashlib.sha256(stage1.read_bytes()).hexdigest()
    )
    assert _raw_member(stage2, "summary.json") == _raw_member(stage1, "summary.json")
    assert _raw_member(stage2, "summary_visual_plan.json") == _raw_member(
        stage1, "summary_visual_plan.json"
    )

    portrait_root = tmp_path / "stage3_media"
    (portrait_root / "portrait").mkdir(parents=True)
    (portrait_root / "portrait" / "scene_0001.png").write_bytes(
        _png("maroon", portrait=True)
    )
    stage3 = build_summary_stage3(
        stage2,
        tmp_path / "summary_package.zip",
        portrait_root,
        _review("scene_0001_landscape", "scene_0001_portrait"),
    )
    stage3_meta = _json_member(stage3, "summary_stage.json")
    assert audit_summary_package(stage3).status == "PASS"
    assert stage3_meta["stage"] == 3
    assert (
        stage3_meta["parent_package_sha256"]
        == hashlib.sha256(stage2.read_bytes()).hexdigest()
    )
    assert _raw_member(stage3, "summary.json") == _raw_member(stage2, "summary.json")
    assert _raw_member(stage3, "landscape/scene_0001.png") == _raw_member(
        stage2, "landscape/scene_0001.png"
    )
    with zipfile.ZipFile(stage3) as archive:
        assert "landscape/scene_0001.png" in archive.namelist()
        assert "portrait/scene_0001.png" in archive.namelist()


def test_stage2_without_required_media_is_partial(tmp_path: Path) -> None:
    stage1 = build_summary_stage1(summary_fixture(), tmp_path / "summary_stage1.zip")
    media_root = tmp_path / "media"
    media_root.mkdir()

    stage2 = build_summary_stage2(
        stage1, tmp_path / "stage2.zip", media_root, _review()
    )

    assert _json_member(stage2, "summary_manifest.json")["status"] == "PARTIAL"


def test_stage1_cli_builds_complete_package(tmp_path: Path, capsys) -> None:
    source = tmp_path / "summary.json"
    source.write_bytes(canonical_json_bytes(summary_fixture()))
    output = tmp_path / "summary_stage1.zip"

    assert stage1_main([str(source), "--output", str(output)]) == 0
    response = json.loads(capsys.readouterr().out)

    assert response["status"] == "COMPLETE"
    assert response["stage"] == 1
    assert audit_summary_package(output).status == "PASS"
