from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from studio.prompt_audit import main
from studio.summary_audit import audit_summary_package
from studio.summary_projection import (
    project_summary_to_image_prompts,
    project_summary_to_story,
    project_summary_to_video_prompts,
    project_summary_to_visual_plan,
)
from tests.contracts.test_summary_projection import summary_fixture


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _package_files() -> dict[str, bytes]:
    summary = summary_fixture()
    story = project_summary_to_story(summary)
    visual = project_summary_to_visual_plan(summary, story)
    image_prompts = project_summary_to_image_prompts(summary, story, visual)
    video_prompts = project_summary_to_video_prompts(summary, story)
    files = {
        "summary.json": _raw(summary), "story.json": _raw(story),
        "visual_plan.json": _raw(visual), "image_prompts.json": _raw(image_prompts),
        "video_prompts.json": _raw(video_prompts),
    }
    manifest = {
        "schema_version": "1.1.0", "prompt_version": "1.5.0", "status": "COMPLETE",
        "parent_package_sha256": None, "source_fingerprints": [],
        "files": [{"path": name, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                   "origin": "summary_projection"} for name, raw in sorted(files.items())],
    }
    files["summary_manifest.json"] = _raw(manifest)
    return files


def test_summary_directory_and_zip_audit_pass(tmp_path: Path) -> None:
    files = _package_files()
    directory = tmp_path / "summary"
    directory.mkdir()
    for name, raw in files.items():
        (directory / name).write_bytes(raw)
    assert audit_summary_package(directory).status == "PASS"

    archive = tmp_path / "summary_package.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, raw in files.items():
            bundle.writestr(name, raw)
    assert audit_summary_package(archive).status == "PASS"


def test_summary_audit_detects_tampering_and_cli_returns_failure(tmp_path: Path, capsys) -> None:
    files = _package_files()
    directory = tmp_path / "summary"
    directory.mkdir()
    for name, raw in files.items():
        (directory / name).write_bytes(raw)
    (directory / "summary.json").write_bytes(files["summary.json"] + b" ")

    result = audit_summary_package(directory)
    assert result.status == "FAIL"
    assert any("size/hash" in error for error in result.errors)
    assert main([str(directory)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output[0]["artifact"] == "summary_package"
