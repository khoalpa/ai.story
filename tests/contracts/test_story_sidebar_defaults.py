from __future__ import annotations

from pathlib import Path


def test_story_sidebar_max_tokens_default_is_32768() -> None:
    content = Path("story/gui/sidebar.py").read_text(encoding="utf-8")

    assert 'st.number_input("Max tokens", min_value=256, value=32768, step=256)' in content


def test_story_sidebar_generation_defaults() -> None:
    sidebar = Path("story/gui/sidebar.py").read_text(encoding="utf-8")
    state = Path("story/gui/state.py").read_text(encoding="utf-8")

    assert 'st.number_input("Timeout (s)", min_value=10, value=360, step=10)' in sidebar
    assert 'STORY_TEST_BEFORE_GENERATE_KEY: False' in state


def test_story_sidebar_does_not_embed_runtime_diagnostics_or_provider_quick_tests() -> None:
    content = Path("story/gui/sidebar.py").read_text(encoding="utf-8")

    assert "render_provider_quick_tests" not in content
    assert "collect_runtime_diagnostics" not in content
    assert "render_runtime_diagnostics_block" not in content
    assert "SidebarSection.RUNTIME" not in content


def test_story_sidebar_random_seed_uses_callback_not_post_widget_assignment() -> None:
    content = Path("story/gui/sidebar.py").read_text(encoding="utf-8")

    assert 'button("Random seed", width="stretch", on_click=_randomize_story_seed)' in content
    assert 'if seed_cols[1].button("Random seed"' not in content


def test_story_sidebar_provider_buttons_are_simplified() -> None:
    content = Path("story/gui/sidebar.py").read_text(encoding="utf-8")

    assert 'st.button("Reset theo profile hiện tại", width="stretch")' in content
    assert '"Áp dụng mặc định profile"' not in content
    assert '"Áp dụng mặc định provider"' not in content
    assert 'st.expander("Cấu hình LLM đã lưu", expanded=False)' in content
    assert '"Lưu cấu hình LLM"' in content
    assert '"Khôi phục cấu hình LLM"' in content


def test_story_default_assets_do_not_depend_on_gui_mode_presets() -> None:
    from story.common import default_brief_filename_for_mode, default_prompt_filename_for_mode
    from story.gui.app_defaults import default_system_prompt

    assert default_brief_filename_for_mode("trend").endswith((".yml", ".yaml"))
    assert default_prompt_filename_for_mode("trend").endswith((".txt", ".prompt"))
    assert default_system_prompt("trend").strip()

