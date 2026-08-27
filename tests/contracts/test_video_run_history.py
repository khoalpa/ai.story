from __future__ import annotations

from datetime import datetime, timezone

from video import run_history


def test_log_paths_are_unique_for_same_output_and_timestamp(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RENDER_VIDEO_HISTORY_DIR", str(tmp_path))
    timestamp = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)

    first = run_history._build_log_file_path(timestamp, "output/story.mp4")
    second = run_history._build_log_file_path(timestamp, "output/story.mp4")

    assert first != second
    assert first.name.endswith(".log")
    assert "story" in first.name


def test_consecutive_run_logs_do_not_overwrite_each_other(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RENDER_VIDEO_HISTORY_DIR", str(tmp_path))

    first = run_history.write_run_log(stdout="first", output_hint="story.mp4")
    second = run_history.write_run_log(stdout="second", output_hint="story.mp4")

    assert first != second
    assert first.read_text(encoding="utf-8") == "first"
    assert second.read_text(encoding="utf-8") == "second"
