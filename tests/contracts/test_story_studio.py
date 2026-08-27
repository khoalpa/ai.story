from __future__ import annotations

import json
from pathlib import Path

from studio.story_studio import load_story_package


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
