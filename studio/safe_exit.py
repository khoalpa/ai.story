"""Safe, session-scoped exit controls for the unified Studio shell."""
from __future__ import annotations

from typing import Any, MutableMapping

EXIT_PENDING_KEY = "studio_exit_pending"
SESSION_CLOSED_KEY = "studio_session_closed"
LAST_JOB_STATUS_KEY = "workspace_last_job_status"


def has_active_job(state: MutableMapping[str, Any]) -> bool:
    """Return whether the shared Audio/Video monitor reports active work."""
    return str(state.get(LAST_JOB_STATUS_KEY) or "idle").strip().casefold() == "running"


def request_exit(state: MutableMapping[str, Any]) -> None:
    state[EXIT_PENDING_KEY] = True


def cancel_exit(state: MutableMapping[str, Any]) -> None:
    state[EXIT_PENDING_KEY] = False


def confirm_exit(state: MutableMapping[str, Any]) -> bool:
    """Close the UI session unless doing so would hide an active job."""
    if has_active_job(state):
        return False
    state[EXIT_PENDING_KEY] = False
    state[SESSION_CLOSED_KEY] = True
    return True


def reopen_session(state: MutableMapping[str, Any]) -> None:
    state[SESSION_CLOSED_KEY] = False
    state[EXIT_PENDING_KEY] = False


def render_safe_exit() -> bool:
    """Render exit controls and return ``True`` while the UI is closed."""
    import streamlit as st

    state = st.session_state
    if bool(state.get(SESSION_CLOSED_KEY)):
        st.info(
            "Phiên làm việc đã được đóng an toàn. Dữ liệu và cấu hình trong phiên "
            "vẫn được giữ; bạn có thể đóng tab trình duyệt."
        )
        st.button(
            "Mở lại phiên làm việc",
            key="studio_reopen_session",
            type="primary",
            on_click=reopen_session,
            args=(state,),
        )
        return True

    st.sidebar.divider()
    if not bool(state.get(EXIT_PENDING_KEY)):
        st.sidebar.button(
            "Thoát ứng dụng",
            key="studio_request_exit",
            on_click=request_exit,
            args=(state,),
            help="Đóng phiên giao diện an toàn; không cưỡng bức dừng tác vụ đang chạy.",
        )
        return False

    active = has_active_job(state)
    st.sidebar.warning(
        "Tác vụ đang chạy. Hãy chờ hoàn tất trước khi thoát."
        if active
        else "Đóng phiên làm việc này? Dữ liệu đã ghi ra đĩa sẽ không bị xóa."
    )
    confirm_column, cancel_column = st.sidebar.columns(2)
    confirm_column.button(
        "Đóng phiên",
        key="studio_confirm_exit",
        type="primary",
        disabled=active,
        on_click=confirm_exit,
        args=(state,),
    )
    cancel_column.button(
        "Hủy",
        key="studio_cancel_exit",
        on_click=cancel_exit,
        args=(state,),
    )
    return False


__all__ = [
    "EXIT_PENDING_KEY",
    "SESSION_CLOSED_KEY",
    "cancel_exit",
    "confirm_exit",
    "has_active_job",
    "render_safe_exit",
    "reopen_session",
    "request_exit",
]
