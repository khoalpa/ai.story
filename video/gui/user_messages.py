from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import streamlit as st


@dataclass(frozen=True)
class GuidanceAction:
    """A short follow-up step shown below a user-facing message."""

    text: str


@dataclass(frozen=True)
class UserMessage:
    """Structured, friendly GUI message for validation and runtime guidance."""

    level: str
    title: str
    body: str
    actions: tuple[GuidanceAction, ...] = ()
    technical_details: str | None = None


def _normalize_actions(actions: Sequence[str] | Sequence[GuidanceAction] | None) -> tuple[GuidanceAction, ...]:
    if not actions:
        return ()
    normalized: list[GuidanceAction] = []
    for item in actions:
        if isinstance(item, GuidanceAction):
            normalized.append(item)
        else:
            text = str(item).strip()
            if text:
                normalized.append(GuidanceAction(text=text))
    return tuple(normalized)


def _render_actions(actions: Iterable[GuidanceAction]) -> None:
    rendered = [f"- {action.text}" for action in actions if action.text.strip()]
    if rendered:
        st.markdown("\n".join(rendered))


def render_user_message(message: UserMessage, *, show_details: bool = False) -> None:
    title = message.title.strip()
    body = message.body.strip()
    content = f"**{title}**\n\n{body}" if title else body

    if message.level == "success":
        st.success(content)
    elif message.level == "warning":
        st.warning(content)
    elif message.level == "info":
        st.info(content)
    else:
        st.error(content)

    _render_actions(message.actions)
    if show_details and message.technical_details:
        with st.expander("Chi tiết kỹ thuật"):
            st.code(message.technical_details)


def show_missing_input(
    field_label: str,
    *,
    hint: str | None = None,
    actions: Sequence[str] | Sequence[GuidanceAction] | None = None,
    stop: bool = False,
) -> None:
    body = f"Cần bổ sung **{field_label}** trước khi tiếp tục."
    if hint:
        body = f"{body} {hint.strip()}"
    render_user_message(
        UserMessage(
            level="warning",
            title="Thiếu đầu vào bắt buộc",
            body=body,
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Điền trường còn thiếu hoặc chọn một nguồn hợp lệ."),
                GuidanceAction("Thử lại sau khi đầu vào đã sẵn sàng."),
            ),
        )
    )
    if stop:
        st.stop()


def show_provider_error(
    provider_name: str,
    *,
    problem: str | None = None,
    actions: Sequence[str] | Sequence[GuidanceAction] | None = None,
    technical_details: str | None = None,
    show_details: bool = False,
    stop: bool = False,
) -> None:
    body = (
        problem.strip()
        if problem and problem.strip()
        else f"{provider_name} chưa khả dụng hoặc chưa được cấu hình đúng."
    )
    render_user_message(
        UserMessage(
            level="error",
            title=f"{provider_name} chưa sẵn sàng",
            body=body,
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Kiểm tra tên model, API base hoặc thông tin xác thực."),
                GuidanceAction("Dùng Kiểm tra hoặc Làm mới trước khi chạy lại."),
            ),
            technical_details=technical_details,
        ),
        show_details=show_details,
    )
    if stop:
        st.stop()


def show_preview_warning(
    subject: str = "preview",
    *,
    reason: str | None = None,
    actions: Sequence[str] | Sequence[GuidanceAction] | None = None,
) -> None:
    body = f"Chưa có {subject.strip()} để hiển thị."
    if reason and reason.strip():
        body = f"{body} {reason.strip()}"
    render_user_message(
        UserMessage(
            level="info",
            title="Chưa có nội dung xem trước",
            body=body,
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Hoàn tất bước trước trong quy trình."),
                GuidanceAction("Làm mới sau khi đầu ra mới được tạo."),
            ),
        )
    )


def show_empty_result(
    result_name: str,
    *,
    actions: Sequence[str] | Sequence[GuidanceAction] | None = None,
) -> None:
    render_user_message(
        UserMessage(
            level="info",
            title="Chưa có kết quả",
            body=f"Chưa có {result_name.strip()}.",
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Hoàn tất bước render trước."),
                GuidanceAction("Kiểm tra nhật ký nếu bạn đang chờ một đầu ra tại đây."),
            ),
        )
    )


def show_path_warning(
    path_label: str,
    *,
    path_value: str | None = None,
    actions: Sequence[str] | Sequence[GuidanceAction] | None = None,
) -> None:
    body = f"Đường dẫn cấu hình cho **{path_label}** đang thiếu hoặc không hợp lệ."
    if path_value:
        body = f"{body} Giá trị hiện tại: `{path_value}`."
    render_user_message(
        UserMessage(
            level="warning",
            title="Cần kiểm tra đường dẫn",
            body=body,
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Xác minh tệp hoặc thư mục vẫn tồn tại."),
                GuidanceAction("Cập nhật thiết lập rồi thử lại."),
            ),
        )
    )


__all__ = [
    "GuidanceAction",
    "UserMessage",
    "render_user_message",
    "show_missing_input",
    "show_provider_error",
    "show_preview_warning",
    "show_empty_result",
    "show_path_warning",
]
