from __future__ import annotations

from pathlib import Path


def test_overview_prioritizes_actions_and_collapses_technical_details() -> None:
    source = Path("studio/overview.py").read_text(encoding="utf-8")
    actions = source.index('st.subheader("Việc cần làm tiếp theo")')
    workflow = source.index('with st.expander("Quy trình và bằng chứng kiểm định"')
    assert actions < workflow
    assert 'with st.expander("Chỉ số bổ sung")' in source
    assert 'with st.expander("Tài nguyên, đường dẫn và trạng thái kỹ thuật"' in source
    assert "render_empty_state(" in source


def test_audio_places_a_clear_summary_before_the_primary_action() -> None:
    source = Path("audio/gui/run_panel.py").read_text(encoding="utf-8")
    summary = source.index('st.markdown("#### Xác nhận trước khi render")')
    action = source.index('st.button("Render audio"', summary)
    assert summary < action
    assert 'disabled=not plain_text.strip()' in source[action:]
    assert 'st.button("Gửi sang Video"' in source


def test_video_places_readiness_and_preview_before_render() -> None:
    source = Path("video/gui/tabs.py").read_text(encoding="utf-8")
    run_tab = source.index("def render_run_tab(")
    checklist = source.index('st.markdown("#### Checklist trước khi render")', run_tab)
    preview = source.index("preview_images = _render_preview_images(inputs)", checklist)
    action = source.index('st.button("Render video"', preview)
    assert checklist < preview < action
    assert 'with st.expander("Xem lỗi cần xử lý"' in source[checklist:action]


def test_story_actions_precede_workflow_evidence() -> None:
    source = Path("studio/story_studio.py").read_text(encoding="utf-8")
    overview = source.index("def _render_overview(")
    actions = source.index('st.subheader("Hành động ưu tiên")', overview)
    evidence = source.index('with st.expander("Quy trình, gate và bằng chứng"', actions)
    assert actions < evidence


def test_audio_and_video_keep_technical_details_collapsed() -> None:
    audio = Path("audio/gui/run_panel.py").read_text(encoding="utf-8")
    video = Path("video/gui/tabs.py").read_text(encoding="utf-8")
    assert 'with st.expander("Chi tiết kỹ thuật của kết quả", expanded=False)' in audio
    assert 'with st.expander(f"Nhật ký sự kiện · {len(events)} mục", expanded=False)' in audio
    assert 'with st.expander("Chi tiết kỹ thuật của kết quả", expanded=False)' in video
    assert 'with st.expander("Nhật ký kỹ thuật"' in video


def test_video_inputs_present_three_clear_steps() -> None:
    source = Path("video/gui/tabs.py").read_text(encoding="utf-8")
    inputs = source.index("def render_inputs_tab(")
    run = source.index("def render_run_tab(", inputs)
    body = source[inputs:run]
    for heading in ("1. Nguồn âm thanh", "2. Hình ảnh", "3. Đầu ra"):
        assert heading in body
