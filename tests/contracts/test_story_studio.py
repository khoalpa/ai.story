from __future__ import annotations

import json
from pathlib import Path

from studio.story_studio import REPORT_SPECS, load_story_package


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
    ):
        assert filename in source or filename in Path("studio/audio_delivery_report.py").read_text(encoding="utf-8")


def test_story_overview_only_maps_missing_story_report_statuses() -> None:
    source = Path("studio/story_studio.py").read_text(encoding="utf-8")
    assert "for key, (_filename, label, _validator) in REPORT_SPECS.items()" in source
    assert "REPORT_SPECS[key][1] for key, value in statuses.items()" not in source
    assert set(REPORT_SPECS) == {"story", "validation", "quality", "anchor"}
