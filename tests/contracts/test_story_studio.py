from __future__ import annotations

import json
from pathlib import Path

from studio.story_images import apply_visual_plan_zone_aliases, visual_plan_image_stems
from studio.story_studio import REPORT_SPECS, load_effective_package, load_story_package


def test_story_package_loader_reports_present_missing_and_invalid_files(tmp_path: Path) -> None:
    (tmp_path / "story.json").write_text(
        json.dumps({"meta": {}, "characters": [], "outline": {}, "script": []}),
        encoding="utf-8",
    )
    (tmp_path / "story_validation.json").write_text("not json", encoding="utf-8")

    reports, statuses = load_story_package(tmp_path)

    assert set(reports) == {"story"}
    assert statuses["story"] == "Có dữ liệu"
    assert statuses["validation"].startswith("Không hợp lệ:")
    assert statuses["quality"] == "Thiếu"
    assert statuses["anchor"] == "Thiếu"


def test_story_package_loader_handles_missing_directory(tmp_path: Path) -> None:
    reports, statuses = load_story_package(tmp_path / "missing")

    assert reports == {}
    assert set(statuses.values()) == {"Không tìm thấy thư mục"}


def test_source_selector_lists_all_supported_override_files() -> None:
    source = Path("studio/story_studio.py").read_text(encoding="utf-8")
    for filename in (
        "story.json",
        "story_validation.json",
        "package_quality_report.json",
        "series_anchor.json",
        "story.audio_quality.json",
        "story.srt",
        "audio_video_handoff.json",
        "video_prompts.json",
    ):
        assert filename in source or filename in Path("studio/audio_delivery_report.py").read_text(encoding="utf-8")


def test_video_prompts_override_replaces_directory_data(tmp_path: Path) -> None:
    (tmp_path / "video_prompts.json").write_text(json.dumps({"source": "directory"}), encoding="utf-8")
    state = {
        "story_override_root": str(tmp_path.resolve()),
        "story_overrides": {"video_prompts": json.dumps({"source": "upload"}).encode()},
    }

    reports, statuses = load_effective_package(tmp_path, state)

    assert reports["video_prompts"] == {"source": "upload"}
    assert statuses["video_prompts"] == "Có dữ liệu · tệp thay thế"


def test_story_overview_only_maps_missing_story_report_statuses() -> None:
    source = Path("studio/story_studio.py").read_text(encoding="utf-8")
    assert "for key, (_filename, label, _validator) in REPORT_SPECS.items()" in source
    assert "REPORT_SPECS[key][1] for key, value in statuses.items()" not in source
    assert set(REPORT_SPECS) == {"story", "validation", "quality", "anchor"}


def test_scene_visual_plan_supplies_active_images_and_zone_reader_aliases(tmp_path: Path) -> None:
    plan = {
        "resolved_mode": "SCENE",
        "assets": [
            {"basename": "cover.png", "zone": None},
            {"basename": "greeting.png", "zone": "GREETING"},
            {"basename": "scene_0001.png", "zone": "OPENING"},
            {"basename": "scene_0002.png", "zone": "DEVELOPMENT"},
            {"basename": "farewell.png", "zone": "FAREWELL"},
            {"basename": "outro.png", "zone": None},
        ],
    }
    (tmp_path / "visual_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    opening = tmp_path / "landscape" / "scene_0001.png"
    catalog = {"landscape": {"scene_0001": opening}, "portrait": {}}

    apply_visual_plan_zone_aliases(catalog, tmp_path)

    assert visual_plan_image_stems(tmp_path) == (
        "cover", "greeting", "scene_0001", "scene_0002", "farewell", "outro",
    )
    assert catalog["landscape"]["opening"] == opening
