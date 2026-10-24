import json
from pathlib import Path

import pytest

from studio.artifact_validation import validate_archive
from studio.overview import build_overview_model
from studio.prompt_contract import load_prompt_contract, prompt_contract_for_version
from studio.story_studio import load_story_package
from studio.story_validation_report import _validate_story_report
from studio.video_prompt_validation import validate_video_prompt_plan
from studio.workflow_package import inspect_directory, inspect_members, read_archive
from studio.workflow_views import visual_bible_summary


def test_contract_is_v416_with_independent_schema_version() -> None:
    contract = load_prompt_contract()
    assert contract.version_label == "4.1.6"
    assert contract.story_schema_version == "4.1.3"
    assert contract.video_prompt_schema_version == "4.1.3"


def test_old_prompt_contract_is_rejected() -> None:
    with pytest.raises(ValueError, match="Chỉ hỗ trợ"):
        prompt_contract_for_version("3.16.13")


@pytest.mark.parametrize(
    ("name", "stage"),
    [("story_stage1.zip", "STAGE1"), ("story_stage2.zip", "STAGE2"),
     ("story.zip", "STAGE3"), ("story_video_prompts.zip", "STAGE4")],
)
def test_v416_template_packages_pass_exact_inspection(name: str, stage: str, sample_archives_dir: Path) -> None:
    path = sample_archives_dir / name
    result = inspect_members(read_archive(path), archive=True)
    assert result["stage"] == stage
    assert result["status"] == "PASS"
    assert validate_archive(path).status == "PASS"


def test_extracted_stage4_package_and_video_spans_pass(sample_stage4_project: Path) -> None:
    output = sample_stage4_project
    assert inspect_directory(output)["status"] == "PASS"
    plan = json.loads((output / "video_prompts.json").read_text(encoding="utf-8"))
    assert validate_video_prompt_plan(plan, root=output)["errors"] == []


def test_overview_reads_v416_report_without_legacy_quality_projection(sample_stage4_project: Path) -> None:
    output = sample_stage4_project
    reports, statuses = load_story_package(output)
    model = build_overview_model(reports, statuses, {}, output_dir=output)
    metrics = dict(model["metrics"])
    assert model["workflow"]["stage"] == "STAGE4"
    assert model["verdict"] == "Gói đạt các phép kiểm tra đã chạy"
    assert metrics["Trạng thái báo cáo"] == "COMPLETE"
    assert metrics["Kiểm định"] == "73/73"
    assert "Chất lượng gói" not in metrics


def test_old_manifest_shape_is_not_admitted() -> None:
    old = {"workflow_manifest.json": b'{"schema_version":"1.0"}'}
    result = inspect_members(old)
    assert result["status"] == "FAIL"
    assert result["compatibility"] == "UNSUPPORTED"


def test_old_validation_report_is_not_opened_in_compatibility_mode() -> None:
    with pytest.raises(ValueError, match="Chỉ hỗ trợ"):
        _validate_story_report({"summary": {}, "quality": {}, "gates": []})


def test_manifest_rejects_non_hex_digest_even_when_length_is_64(sample_archives_dir: Path) -> None:
    members = read_archive(sample_archives_dir / "story_stage1.zip")
    manifest = json.loads(members["manifest.json"])
    manifest["files"][0]["sha256"] = "z" * 64
    changed = dict(members)
    changed["manifest.json"] = json.dumps(manifest).encode()
    result = inspect_members(changed)
    assert result["status"] == "FAIL"
    assert next(row for row in result["checks"] if row["check"] == "manifest_files")["status"] == "FAIL"


def test_model_default_images_are_checked_by_orientation_not_fixed_pixels(sample_archives_dir: Path) -> None:
    result = inspect_members(read_archive(sample_archives_dir / "story.zip"), archive=True)
    assert next(row for row in result["checks"] if row["check"] == "image_files")["status"] == "PASS"


def test_visual_bible_view_uses_v416_visual_plan_shape(sample_stage4_project: Path) -> None:
    output = sample_stage4_project
    plan = json.loads((output / "visual_plan.json").read_text(encoding="utf-8"))
    summary = visual_bible_summary(plan, root=output)
    assert summary["status"] == "PASS"
    assert summary["characters"] == summary["reference_passed"] == 3
    assert summary["assets"] == summary["landscape_passed"] == 10
    assert summary["story_links"] == "PASS"
