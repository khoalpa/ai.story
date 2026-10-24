from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from video.story_package_v416 import load_package_bytes, load_project_directory


@pytest.mark.parametrize("name,stage", [
    ("story_stage1.zip", "STAGE1"),
    ("story_stage2.zip", "STAGE2"),
    ("story.zip", "STAGE3"),
    ("story_video_prompts.zip", "STAGE4"),
])
def test_video_opens_verified_v416_sample_packages(name: str, stage: str, sample_archives_dir: Path) -> None:
    members, inspection = load_package_bytes((sample_archives_dir / name).read_bytes())
    assert "story.json" in members
    assert inspection["status"] == "PASS"
    assert inspection["compatibility"] == "NATIVE_CURRENT"
    assert inspection["stage"] == stage


def test_video_resolves_extracted_v416_package(sample_stage4_project: Path) -> None:
    inputs, inspection = load_project_directory(sample_stage4_project)
    assert inspection["stage"] == "STAGE4"
    assert inputs.story_json.is_file()
    assert inputs.visual_plan_json and inputs.visual_plan_json.is_file()
    assert inputs.video_prompts_json and inputs.video_prompts_json.is_file()
    assert inputs.cover("16x9").name == "cover.png"
    assert inputs.cover("9x16").name == "cover.png"


def test_video_rejects_zip_without_v416_manifest(tmp_path: Path) -> None:
    package = tmp_path / "old.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("story.json", '{"schema_version":"3.16"}')
    with pytest.raises(ValueError, match="v4.1.6"):
        load_package_bytes(package.read_bytes())


def test_video_rejects_directory_without_v416_manifest(tmp_path: Path) -> None:
    (tmp_path / "story.json").write_text('{"schema_version":"3.16"}', encoding="utf-8")
    with pytest.raises(ValueError, match="v4.1.6"):
        load_project_directory(tmp_path)
