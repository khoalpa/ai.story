from __future__ import annotations

from pathlib import Path
from typing import Any, MutableMapping

import streamlit as st

from audio.gui.user_messages import UserMessage, render_user_message
from audio.validate_plain_script import LineIssue, validate_script
from studio.project_context import PROJECT_DIRECTORY_KEY

from .helpers import (
    convert_canonical_to_plain_text,
    convert_canonical_to_raw_text,
    convert_raw_to_plain_text,
    save_uploaded_text,
)
from .state import (
    PENDING_PLAIN_SCRIPT_KEY,
    PLAIN_SCRIPT_TEXT_KEY,
    audio_session,
)

CANONICAL_PROJECT_SOURCE_KEY = "audio_canonical_project_source"


def load_project_canonical_default(
    state: MutableMapping[str, Any],
) -> Path | None:
    """Load project story.json once per selected project without clobbering edits."""
    project_text = str(state.get(PROJECT_DIRECTORY_KEY) or "").strip()
    if not project_text:
        return None
    story_path = (Path(project_text).expanduser() / "story.json").resolve()
    source = str(story_path)
    if state.get(CANONICAL_PROJECT_SOURCE_KEY) == source:
        return story_path if story_path.is_file() else None
    if not story_path.is_file():
        return None
    text = story_path.read_text(encoding="utf-8-sig")
    state["canonical_json_text"] = text
    state["canonical_editor"] = text
    state[CANONICAL_PROJECT_SOURCE_KEY] = source
    return story_path


def _sync_editor_state(state_key: str, editor_key: str) -> None:
    if editor_key not in st.session_state:
        st.session_state[editor_key] = st.session_state.get(state_key, "")


def _load_uploaded_text(uploaded_file, state_key: str, editor_key: str) -> None:
    if uploaded_file is None:
        return
    text = save_uploaded_text(uploaded_file)
    st.session_state[state_key] = text
    st.session_state[editor_key] = text


def _apply_pending_plain_script() -> None:
    session = audio_session()
    pending = st.session_state.pop(PENDING_PLAIN_SCRIPT_KEY, None)
    if pending is not None:
        session.plain_script_text = pending
        session.plain_script_editor = pending
        session.last_plain_script = pending


def _issue_rows(issues: list[LineIssue]) -> list[dict[str, object]]:
    return [
        {
            "Line": issue.line_no if issue.line_no > 0 else "Whole script",
            "Message": issue.message,
            "Source": issue.line_text,
        }
        for issue in issues
    ]


def render_workspace_tab() -> None:
    _apply_pending_plain_script()

    tab_canonical, tab_plain, tab_raw = st.tabs(["Canonical JSON", "Plain Script", "Raw Text"])

    with tab_plain:
        _sync_editor_state(PLAIN_SCRIPT_TEXT_KEY, "plain_script_editor")
        uploaded_plain = st.file_uploader("Upload plain script (.txt)", type=["txt"], key="plain_script_upload")
        _load_uploaded_text(uploaded_plain, PLAIN_SCRIPT_TEXT_KEY, "plain_script_editor")

        st.text_area(
            "Plain script",
            height=460,
            key="plain_script_editor",
        )
        session = audio_session()
        session.plain_script_text = st.session_state.get("plain_script_editor", "") or ""
        validation = validate_script(session.plain_script_text.splitlines())

        if validation.errors:
            st.error(
                f"Syntax check found {len(validation.errors)} error(s). "
                "Fix them before sending this script to the Run panel."
            )
            st.dataframe(_issue_rows(validation.errors), width="stretch", hide_index=True)
        elif session.plain_script_text.strip():
            st.success("Syntax check passed. This script can be sent to the Run panel.")

        if validation.warnings:
            with st.expander(f"Warnings ({len(validation.warnings)})"):
                st.dataframe(_issue_rows(validation.warnings), width="stretch", hide_index=True)

        cols = st.columns(2)
        with cols[0]:
            if st.button(
                "Use this plain script",
                width="stretch",
                disabled=not validation.ok,
                help="Fix the syntax errors shown above before continuing." if not validation.ok else None,
            ):
                session = audio_session()
                selected_text = session.plain_script_text
                session.last_plain_script = selected_text
                session.run_plain_text = selected_text
                st.session_state["pending_run_plain_text"] = selected_text
                st.success("Updated the Run panel.")
                st.rerun()
        with cols[1]:
            st.download_button(
                "Download plain script",
                data=audio_session().plain_script_text.encode("utf-8"),
                file_name="script.txt",
                mime="text/plain",
                width="stretch",
            )
    with tab_canonical:
        project_story: Path | None = None
        try:
            project_story = load_project_canonical_default(st.session_state)
        except (OSError, UnicodeError) as exc:
            st.warning(f"Không thể đọc story.json từ Thư mục dữ liệu dự án: {exc}")
        _sync_editor_state("canonical_json_text", "canonical_editor")
        if project_story is not None:
            st.caption(f"Mặc định từ Thư mục dữ liệu dự án · `{project_story}`")
        uploaded_canonical = st.file_uploader("Upload canonical JSON", type=["json"], key="canonical_upload")
        _load_uploaded_text(uploaded_canonical, "canonical_json_text", "canonical_editor")

        st.text_area(
            "Canonical JSON",
            height=460,
            key="canonical_editor",
        )
        st.session_state["canonical_json_text"] = st.session_state.get("canonical_editor", "") or ""

        canonical_actions = st.columns(2)
        with canonical_actions[0]:
            if st.button("Convert canonical -> plain", width="stretch"):
                try:
                    plain_text = convert_canonical_to_plain_text(st.session_state.get("canonical_json_text", "") or "")
                except Exception as exc:
                    render_user_message(
                        UserMessage(
                            level="error",
                            title="Could not convert canonical to plain script",
                            body="The current canonical JSON is invalid or missing required fields.",
                            technical_details=str(exc),
                        ),
                        show_details=True,
                    )
                else:
                    st.session_state[PENDING_PLAIN_SCRIPT_KEY] = plain_text
                    st.rerun()
        with canonical_actions[1]:
            if st.button("Convert canonical -> raw", width="stretch"):
                try:
                    raw_text = convert_canonical_to_raw_text(st.session_state.get("canonical_json_text", "") or "")
                except Exception as exc:
                    render_user_message(
                        UserMessage(
                            level="error",
                            title="Could not convert canonical to raw text",
                            body="The current canonical JSON is invalid or missing required fields.",
                            technical_details=str(exc),
                        ),
                        show_details=True,
                    )
                else:
                    st.session_state["raw_text"] = raw_text
                    st.session_state["raw_editor"] = raw_text
                    st.rerun()

    with tab_raw:
        _sync_editor_state("raw_text", "raw_editor")
        uploaded_raw = st.file_uploader("Upload raw text", type=["txt", "md"], key="raw_upload")
        _load_uploaded_text(uploaded_raw, "raw_text", "raw_editor")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            default_raw_title = st.session_state.get("raw_title") or st.session_state.get("workspace_title", "")
            raw_title = st.text_input("Title", key="raw_title", value=default_raw_title)
        with c2:
            raw_default_voice = st.selectbox("Default voice tag", ["NARRATOR", "FEMALE", "MALE"])
        with c3:
            raw_default_lang = st.selectbox("Default language tag", ["VI", "EN"])
        with c4:
            include_header = st.checkbox("Include header", value=True)

        st.text_area("Raw text", height=430, key="raw_editor")
        st.session_state["raw_text"] = st.session_state.get("raw_editor", "") or ""

        if st.button("Convert raw -> plain", width="stretch"):
            plain_text = convert_raw_to_plain_text(
                st.session_state.get("raw_text", "") or "",
                title=raw_title,
                default_voice=raw_default_voice,
                default_lang=raw_default_lang,
                include_header=include_header,
            )
            st.session_state[PENDING_PLAIN_SCRIPT_KEY] = plain_text
            st.rerun()
