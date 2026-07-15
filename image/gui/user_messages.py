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
        with st.expander("Technical details"):
            st.code(message.technical_details)


def show_missing_input(
    field_label: str,
    *,
    hint: str | None = None,
    actions: Sequence[str] | Sequence[GuidanceAction] | None = None,
    stop: bool = False,
) -> None:
    body = f"Please provide **{field_label}** before continuing."
    if hint:
        body = f"{body} {hint.strip()}"
    render_user_message(
        UserMessage(
            level="warning",
            title="Missing required input",
            body=body,
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Fill in the missing field or choose a valid source."),
                GuidanceAction("Try the action again after the input is ready."),
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
        else f"{provider_name} is currently unavailable or not configured correctly."
    )
    render_user_message(
        UserMessage(
            level="error",
            title=f"{provider_name} is not ready",
            body=body,
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Check the model name, API base, or authentication settings."),
                GuidanceAction("Use the Test or Refresh action in the sidebar before running again."),
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
    body = f"The {subject.strip()} is not available yet."
    if reason and reason.strip():
        body = f"{body} {reason.strip()}"
    render_user_message(
        UserMessage(
            level="info",
            title="Nothing to preview yet",
            body=body,
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Run the previous step in the pipeline first."),
                GuidanceAction("Refresh the page after new output is generated."),
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
            title="No result yet",
            body=f"No {result_name.strip()} is available yet.",
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Complete the run step first."),
                GuidanceAction("Check the run log if you expected output here."),
            ),
        )
    )


def show_path_warning(
    path_label: str,
    *,
    path_value: str | None = None,
    actions: Sequence[str] | Sequence[GuidanceAction] | None = None,
) -> None:
    body = f"The configured path for **{path_label}** is missing or invalid."
    if path_value:
        body = f"{body} Current value: `{path_value}`."
    render_user_message(
        UserMessage(
            level="warning",
            title="Path needs attention",
            body=body,
            actions=_normalize_actions(actions)
            or (
                GuidanceAction("Verify that the file or folder exists."),
                GuidanceAction("Update the setting and try the action again."),
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
