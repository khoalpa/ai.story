from __future__ import annotations

from studio.summary_preview import estimate_summary_timing, preview_projection_mapping
from tests.contracts.test_summary_projection import summary_fixture


def test_timing_estimate_reports_target_delta() -> None:
    summary = summary_fixture()
    timing = estimate_summary_timing(summary, rate_per_minute=150)

    assert timing["word_count"] > 0
    assert timing["estimated_minutes"] > 0
    assert timing["target_minutes"] == 1
    assert timing["delta_percent"] is not None


def test_projection_preview_links_every_story_layer() -> None:
    rows = preview_projection_mapping(summary_fixture())

    assert len(rows) == 8
    assert [row["story_script_id"] for row in rows] == [f"s{index:04d}" for index in range(1, 9)]
    assert [row["scene"] for row in rows] == [f"scene_{index:04d}.png" for index in range(1, 9)]
    assert [row["video_clip"] for row in rows] == [f"clip_{index:04d}" for index in range(1, 9)]
    assert all(row["narration_ids"] == ["narration_0001"] for row in rows)
