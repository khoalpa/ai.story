from __future__ import annotations

import json
import zipfile
from pathlib import Path

from studio.summary_audit import audit_summary_package
from studio.summary_cli import audit_main, build_main, migrate_main, project_main
from studio.summary_migration import migrate_summary_v100_to_v110
from studio.summary_package import build_summary_package, canonical_json_bytes
from studio.summary_schema import validate_summary_document
from tests.contracts.test_summary_projection import summary_fixture


def test_deterministic_package_builds_and_audits(tmp_path: Path) -> None:
    summary = summary_fixture()
    first = build_summary_package(summary, tmp_path / "first.zip")
    second = build_summary_package(summary, tmp_path / "second.zip")

    assert first.read_bytes() == second.read_bytes()
    assert audit_summary_package(first).status == "PASS"
    with zipfile.ZipFile(first) as archive:
        assert "summary_manifest.json" in archive.namelist()
        assert "summary_visual_plan.json" in archive.namelist()
        visual_plan = json.loads(archive.read("summary_visual_plan.json"))
        assert visual_plan["image_mode"] == "SCENE"
        report = json.loads(archive.read("projection_report.json"))
        assert report["status"] == "COMPLETE"


def test_summary_cli_build_project_and_audit(tmp_path: Path, capsys) -> None:
    source = tmp_path / "summary.json"
    source.write_bytes(canonical_json_bytes(summary_fixture()))
    package = tmp_path / "summary_package.zip"
    assert build_main([str(source), "--output", str(package)]) == 0
    capsys.readouterr()
    assert audit_main([str(package)]) == 0
    capsys.readouterr()
    output = tmp_path / "projection"
    assert (
        project_main(
            [str(source), "--output", str(output), "--targets", "story", "video"]
        )
        == 0
    )
    assert (output / "story.json").is_file()
    assert (output / "video_prompts.json").is_file()

    image_output = tmp_path / "image_projection"
    assert (
        project_main([str(source), "--output", str(image_output), "--targets", "image"])
        == 0
    )
    assert (image_output / "summary_render_plan.json").is_file()


def test_v100_migration_adds_v110_fields_without_mutating_source(
    tmp_path: Path, capsys
) -> None:
    current = summary_fixture()
    legacy = {
        key: value
        for key, value in current.items()
        if key not in {"claim_relations", "numeric_facts", "glossary"}
    }
    legacy["schema_version"] = "1.0.0"
    legacy["prompt_version"] = "1.2.0"
    for key in ("citation_style", "scene_density_seconds", "max_scenes"):
        legacy["meta"].pop(key)
    for source in legacy["sources"]:
        for key in ("authors", "published_at", "publisher", "url", "accessed_at"):
            source.pop(key)

    migrated = migrate_summary_v100_to_v110(legacy)
    assert validate_summary_document(migrated) == []
    assert legacy["schema_version"] == "1.0.0"

    source = tmp_path / "legacy.json"
    destination = tmp_path / "current.json"
    source.write_bytes(canonical_json_bytes(legacy))
    assert migrate_main([str(source), "--output", str(destination)]) == 0
    capsys.readouterr()
    assert (
        validate_summary_document(json.loads(destination.read_text(encoding="utf-8")))
        == []
    )
