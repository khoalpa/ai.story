"""Small, reusable presentation patterns for Streamlit workspaces."""
from __future__ import annotations

from html import escape
from typing import Literal

StatusTone = Literal["neutral", "info", "success", "warning", "error"]
_STATUS_TONES = {"neutral", "info", "success", "warning", "error"}
PIPELINE_STEPS = ("Nội dung", "Audio", "Bàn giao", "Video", "Hoàn tất")
RUN_STATUS_PRESENTATION = {
    "idle": ("Chưa bắt đầu", "neutral"),
    "running": ("Đang xử lý", "info"),
    "warning": ("Cần chú ý", "warning"),
    "failed": ("Bị chặn", "error"),
    "blocked": ("Bị chặn", "error"),
    "completed": ("Hoàn tất", "success"),
}


def _safe(value: object) -> str:
    return escape(str(value), quote=True)


def status_badge_html(label: str, *, tone: StatusTone = "neutral") -> str:
    """Return an escaped status badge suitable for ``st.html``."""
    normalized_tone = tone if tone in _STATUS_TONES else "neutral"
    return (
        f'<span class="studio-status-badge studio-status-badge--{normalized_tone}">'
        f"{_safe(label)}</span>"
    )


def render_workspace_header(
    title: str,
    description: str,
    *,
    eyebrow: str = "Không gian làm việc",
    status: str | None = None,
    status_tone: StatusTone = "neutral",
) -> None:
    """Render the shared title, description, and optional status treatment."""
    import streamlit as st

    badge = status_badge_html(status, tone=status_tone) if status else ""
    st.html(
        '<section class="studio-workspace-header">'
        '<div class="studio-workspace-header__content">'
        f'<div class="studio-workspace-header__eyebrow">{_safe(eyebrow)}</div>'
        f'<h2 class="studio-workspace-header__title">{_safe(title)}</h2>'
        f'<p class="studio-workspace-header__description">{_safe(description)}</p>'
        f"</div>{badge}</section>"
    )


def render_empty_state(title: str, description: str, *, icon: str = "○") -> None:
    """Render a calm, actionable empty state without implying an error."""
    import streamlit as st

    st.html(
        '<section class="studio-empty-state">'
        f'<div class="studio-empty-state__icon" aria-hidden="true">{_safe(icon)}</div>'
        f'<div class="studio-empty-state__title">{_safe(title)}</div>'
        f'<div class="studio-empty-state__description">{_safe(description)}</div>'
        "</section>"
    )


def render_summary_card(label: str, value: object, *, detail: str = "") -> None:
    """Render a compact non-interactive summary card."""
    import streamlit as st

    detail_html = f'<div class="studio-summary-card__detail">{_safe(detail)}</div>' if detail else ""
    st.html(
        '<section class="studio-summary-card">'
        f'<div class="studio-summary-card__label">{_safe(label)}</div>'
        f'<div class="studio-summary-card__value">{_safe(value)}</div>'
        f"{detail_html}</section>"
    )


def confirm_destructive_action(
    label: str,
    *,
    key: str,
    help_text: str = "Thao tác này có thể khó hoàn tác.",
) -> bool:
    """Require an explicit checkbox before enabling a destructive action."""
    import streamlit as st

    return bool(st.checkbox(label, key=key, help=help_text))


def render_pipeline_progress(active_step: int) -> None:
    """Render the common Story-to-media progress rail."""
    import streamlit as st

    active = max(1, min(len(PIPELINE_STEPS), int(active_step)))
    items = []
    for index, label in enumerate(PIPELINE_STEPS, start=1):
        state = "complete" if index < active else "active" if index == active else "pending"
        marker = "✓" if state == "complete" else str(index)
        items.append(
            f'<li class="studio-progress__item studio-progress__item--{state}"'
            f' aria-current="{"step" if state == "active" else "false"}">'
            f'<span class="studio-progress__marker">{marker}</span>'
            f'<span class="studio-progress__label">{_safe(label)}</span></li>'
        )
    st.html(
        '<nav class="studio-progress" aria-label="Tiến độ sản xuất">'
        f'<ol class="studio-progress__list">{"".join(items)}</ol></nav>'
    )


def run_status_presentation(status: object) -> tuple[str, StatusTone]:
    """Map runtime status values to the shared user-facing vocabulary."""
    normalized = str(status or "idle").strip().casefold()
    label, tone = RUN_STATUS_PRESENTATION.get(normalized, ("Cần chú ý", "warning"))
    return label, tone  # type: ignore[return-value]


def render_global_run_feedback(state: object) -> None:
    """Show durable feedback for the latest Audio/Video run in the shell."""
    import streamlit as st

    status = str(state.get("workspace_last_job_status") or "idle")  # type: ignore[attr-defined]
    if status == "idle":
        return
    app = str(state.get("workspace_last_job_app") or "Tác vụ")  # type: ignore[attr-defined]
    stage = str(state.get("workspace_last_job_stage") or "Đang xử lý")  # type: ignore[attr-defined]
    error = str(state.get("workspace_last_job_error") or "")  # type: ignore[attr-defined]
    output = str(state.get("workspace_last_job_output") or "")  # type: ignore[attr-defined]
    try:
        progress = max(0, min(100, int(state.get("workspace_last_job_progress") or 0)))  # type: ignore[attr-defined]
    except (TypeError, ValueError):
        progress = 0
    label, tone = run_status_presentation(status)

    with st.container(border=True):
        left, right = st.columns([5, 1])
        left.markdown(f"**{app} · {stage}**")
        right.html(status_badge_html(label, tone=tone))
        if status == "running":
            st.progress(progress / 100, text=f"{label} · {progress}%")
            st.caption("Có thể chuyển workspace; trạng thái gần nhất vẫn được giữ trong phiên.")
        elif status == "completed":
            st.success("Tác vụ đã hoàn tất." + (f" Đầu ra: `{output}`" if output else ""))
        else:
            st.error("Tác vụ chưa hoàn tất. Cấu hình hiện tại được giữ lại để bạn kiểm tra và thử lại.")
            if error:
                with st.expander("Nguyên nhân kỹ thuật", expanded=False):
                    st.code(error)

            workspace = "Audio Studio" if app.casefold() == "audio" else "Video Studio"

            def prepare_retry() -> None:
                from studio.navigation import navigate_to

                navigate_to(st.session_state, workspace, view="run")

            st.button(
                f"Mở {app} để thử lại",
                key="studio_retry_last_run",
                on_click=prepare_retry,
            )


__all__ = [
    "StatusTone",
    "confirm_destructive_action",
    "render_empty_state",
    "render_pipeline_progress",
    "render_global_run_feedback",
    "render_summary_card",
    "render_workspace_header",
    "status_badge_html",
    "run_status_presentation",
]
