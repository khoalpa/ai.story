from __future__ import annotations

from studio.ui_components import (
    RUN_STATUS_PRESENTATION,
    run_status_presentation,
    status_badge_html,
)


def test_status_badge_escapes_user_visible_content() -> None:
    html = status_badge_html('<script>alert("x")</script>', tone="success")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "studio-status-badge--success" in html


def test_status_badge_falls_back_to_neutral_tone() -> None:
    html = status_badge_html("Không xác định", tone="unknown")  # type: ignore[arg-type]
    assert "studio-status-badge--neutral" in html


def test_run_statuses_use_one_user_facing_vocabulary() -> None:
    assert set(RUN_STATUS_PRESENTATION) == {
        "idle", "running", "warning", "failed", "blocked", "completed"
    }
    assert run_status_presentation("idle") == ("Chưa bắt đầu", "neutral")
    assert run_status_presentation("running") == ("Đang xử lý", "info")
    assert run_status_presentation("warning") == ("Cần chú ý", "warning")
    assert run_status_presentation("failed") == ("Bị chặn", "error")
    assert run_status_presentation("completed") == ("Hoàn tất", "success")
    assert run_status_presentation("unknown") == ("Cần chú ý", "warning")
