from __future__ import annotations

from pathlib import Path


def test_story_main_panel_exposes_project_tools_view() -> None:
    content = Path("story/gui/main_panel.py").read_text(encoding="utf-8")

    assert '"Project Tools"' in content
    assert "render_project_tools_workspace(embedded=True)" in content


def test_story_tools_expose_full_canonical_validation() -> None:
    content = Path("story/gui/tabs.py").read_text(encoding="utf-8")

    assert '"Validate canonical"' in content
    assert "validate_script_length_rule(authoring)" in content
    assert "extract_auto_repair_log(authoring)" in content


def test_story_convert_raw_exposes_title_hint() -> None:
    content = Path("story/gui/tabs.py").read_text(encoding="utf-8")

    assert 'st.text_input("Title hint", key="story_tool_title_hint")' in content
    assert 'title_hint=str(title_hint or "")' in content
