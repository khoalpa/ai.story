from __future__ import annotations

from pathlib import Path

from studio.story_studio import STORY_STUDIO_SECTION_INTROS, STORY_STUDIO_SECTIONS


def test_story_studio_section_order_is_stable() -> None:
    assert STORY_STUDIO_SECTIONS == (
        "Tổng quan",
        "Gói & quy trình",
        "Nội dung",
        "Kiểm định",
        "Chất lượng",
        "Tài nguyên",
        "Visual Bible",
        "Kế hoạch video",
        "Âm thanh & phụ đề",
        "Video đầu ra",
        "Series",
        "Công cụ",
    )


def test_each_story_section_has_distinct_heading_and_caption() -> None:
    assert set(STORY_STUDIO_SECTION_INTROS) == set(STORY_STUDIO_SECTIONS)
    headings = [STORY_STUDIO_SECTION_INTROS[section][0] for section in STORY_STUDIO_SECTIONS]
    assert len(set(headings)) == len(STORY_STUDIO_SECTIONS)
    for heading, caption in STORY_STUDIO_SECTION_INTROS.values():
        assert heading.strip()
        assert caption.strip()


def test_integrated_shell_renders_navigation_before_story_workspace() -> None:
    shell = Path("studio/gui_entry.py").read_text(encoding="utf-8")
    navigation = shell.index('if selected == "Story Studio":')
    renderers = shell.index("renderers = {")
    assert navigation < renderers
    assert "render_story_studio_navigation()" in shell[navigation:renderers]
    assert "show_navigation=False" in shell


def test_source_selector_is_rendered_only_for_overview() -> None:
    source = Path("studio/story_studio.py").read_text(encoding="utf-8")
    overview_branch = source.index('if section == "Tổng quan":')
    selector_call = source.index("reports, statuses = _render_source_selector()", overview_branch)
    background_load = source.index("reports, statuses = _load_source_from_session()", selector_call)

    assert overview_branch < selector_call < background_load
    assert "return" in source[selector_call:background_load]
