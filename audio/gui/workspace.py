from __future__ import annotations

import streamlit as st

from audio.gui.user_messages import UserMessage, render_user_message
from .helpers import convert_canonical_to_plain_text, convert_raw_to_plain_text, save_uploaded_text
from .state import (
    AUDIO_LOCK_TO_STORY_HANDOFF_KEY,
    PENDING_PLAIN_SCRIPT_KEY,
    PLAIN_SCRIPT_TEXT_KEY,
    RUN_PLAIN_TEXT_KEY,
    AUDIO_LAST_AUTO_PLAIN_SCRIPT_KEY,
    audio_session,
)


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


def _apply_story_handoff_prefill() -> None:
    session = audio_session()
    incoming = st.session_state.get("workspace_story_plain_script_text", "") or ""
    previous_auto = session.auto_plain_script
    lock_to_handoff = session.lock_to_story_handoff
    if not incoming:
        return

    current_plain = session.plain_script_text
    current_editor = st.session_state.get("plain_script_editor", "") or ""
    current_run = session.run_plain_text
    current_last = session.last_plain_script

    already_synced = (
        incoming == previous_auto
        and current_plain == incoming
        and current_editor == incoming
        and current_run == incoming
        and current_last == incoming
    )
    if already_synced:
        return

    if lock_to_handoff or not current_plain or current_plain == previous_auto:
        session.plain_script_text = incoming
    if lock_to_handoff or not current_editor or current_editor == previous_auto:
        st.session_state["plain_script_editor"] = incoming
    if lock_to_handoff or not current_run or current_run == previous_auto:
        session.run_plain_text = incoming
    if lock_to_handoff or not current_last or current_last == previous_auto:
        session.last_plain_script = incoming

    session.auto_plain_script = incoming


def render_workspace_tab() -> None:
    _apply_pending_plain_script()
    _apply_story_handoff_prefill()

    st.checkbox(
        "Lock input to Story handoff",
        key=AUDIO_LOCK_TO_STORY_HANDOFF_KEY,
        help="When enabled, the plain script received from Story can keep updating and overwrite the Audio input/run area.",
    )

    tab_plain, tab_canonical, tab_raw = st.tabs(["Plain Script", "Canonical JSON", "Raw Text"])

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

        cols = st.columns(3)
        with cols[0]:
            if st.button("Use this plain script", width="stretch"):
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
                file_name="story.txt",
                mime="text/plain",
                width="stretch",
            )
        with cols[2]:
            st.code(audio_session().plain_script_text[:1200] or "", language="text")

    with tab_canonical:
        _sync_editor_state("canonical_json_text", "canonical_editor")
        uploaded_canonical = st.file_uploader("Upload canonical JSON", type=["json"], key="canonical_upload")
        _load_uploaded_text(uploaded_canonical, "canonical_json_text", "canonical_editor")

        st.text_area(
            "Canonical JSON",
            height=460,
            key="canonical_editor",
        )
        st.session_state["canonical_json_text"] = st.session_state.get("canonical_editor", "") or ""

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
