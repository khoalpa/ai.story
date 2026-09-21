from __future__ import annotations

from pathlib import Path


def test_shell_renders_global_feedback_below_pipeline_progress() -> None:
    source = Path("studio/gui_entry.py").read_text(encoding="utf-8")
    progress = source.index("render_pipeline_progress(")
    feedback = source.index("render_global_run_feedback(")
    assert progress < feedback


def test_retry_prepares_run_view_without_executing_a_job() -> None:
    source = Path("studio/ui_components.py").read_text(encoding="utf-8")
    retry = source.index("def prepare_retry()")
    body = source[retry:source.index("st.button(", retry)]
    assert 'navigate_to(st.session_state, workspace, view="run")' in body
    assert "run_video_job" not in body
    assert "run_audio_job" not in body


def test_failed_run_feedback_returns_user_to_the_correct_run_view() -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string(
        "from studio.ui_components import render_global_run_feedback\n"
        "import streamlit as st\n"
        "render_global_run_feedback(st.session_state)"
    )
    app.session_state["workspace_last_job_status"] = "failed"
    app.session_state["workspace_last_job_app"] = "Video"
    app.session_state["workspace_last_job_stage"] = "Render"
    app.session_state["workspace_last_job_error"] = "ffmpeg failed"
    app.run()
    assert not app.exception
    retry = next(button for button in app.button if button.label == "Mở Video để thử lại")
    retry.click().run()
    assert app.session_state["studio_workspace"] == "Video Studio"
    assert app.session_state["video_embedded_view_selector"] == "run"
