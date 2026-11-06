from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from studio.summary_audit import audit_summary_package
from studio.summary_media import (
    REVIEW_CHECKS,
    build_render_plan,
    inspect_rendered_media,
    validate_render_plan,
)
from studio.summary_package import build_summary_members, build_summary_package
from studio.summary_visual import build_summary_visual_plan
from tests.contracts.test_summary_projection import summary_fixture


def _png(width: int = 160, height: int = 90, color: str = "navy") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return output.getvalue()


def _approval(asset_id: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "assets": [
            {"asset_id": asset_id, "checks": {name: "PASS" for name in REVIEW_CHECKS}}
        ],
    }


def test_render_plan_uses_root_orientation_directories() -> None:
    summary = summary_fixture()
    plan = build_render_plan(summary, build_summary_visual_plan(summary))

    assert validate_render_plan(plan) == []
    assert plan["assets"][0]["output_path"] == "landscape/scene_0001.png"
    assert not plan["assets"][0]["output_path"].startswith("media/")


def test_media_inspection_requires_semantic_review_for_complete() -> None:
    summary = summary_fixture()
    plan = build_render_plan(summary, build_summary_visual_plan(summary))
    asset = plan["assets"][0]
    media = {asset["output_path"]: _png()}

    _, review, status = inspect_rendered_media(plan, media)
    assert status == "PARTIAL"
    assert review["assets"][0]["status"] == "PENDING_REVIEW"

    _, approved, status = inspect_rendered_media(
        plan, media, _approval(asset["asset_id"])
    )
    assert status == "COMPLETE"
    assert approved["metrics"]["coverage_percent"] == 100


def test_media_aware_package_is_complete_and_audits(tmp_path: Path) -> None:
    summary = summary_fixture()
    visual = build_summary_visual_plan(summary)
    render = build_render_plan(summary, visual)
    asset = render["assets"][0]
    media = {asset["output_path"]: _png()}
    output = tmp_path / "summary.zip"

    build_summary_package(
        summary,
        output,
        summary_visual_plan=visual,
        media=media,
        media_review=_approval(asset["asset_id"]),
    )

    assert audit_summary_package(output).status == "PASS"
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "landscape/scene_0001.png" in names
        assert not any(name.startswith("media/") for name in names)
        manifest = json.loads(archive.read("summary_manifest.json"))
        assert manifest["status"] == "COMPLETE"
        packaged_render = json.loads(archive.read("summary_render_plan.json"))
        assert packaged_render["assets"][0]["status"] == "VALIDATED"
        media_row = next(
            row for row in manifest["files"] if row["path"].endswith("scene_0001.png")
        )
        assert media_row["orientation"] == "landscape"
        assert media_row["review_status"] == "PASS"


def test_package_without_rendered_images_is_partial() -> None:
    members = build_summary_members(summary_fixture())
    manifest = json.loads(members["summary_manifest.json"])

    assert manifest["status"] == "PARTIAL"
    assert "summary_render_plan.json" in members
