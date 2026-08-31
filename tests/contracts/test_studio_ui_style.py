from __future__ import annotations

from pathlib import Path

from studio.ui_style import STUDIO_STYLE


def test_shared_style_defines_common_tokens_and_surfaces() -> None:
    for token in (
        "--studio-space-1",
        "--studio-radius-control",
        "--studio-radius-surface",
        "--studio-border",
    ):
        assert token in STUDIO_STYLE
    for surface in ('[data-testid="stMetric"]', '[data-testid="stAlert"]', ".story-heading"):
        assert surface in STUDIO_STYLE


def test_shell_injects_style_before_workspace_rendering() -> None:
    shell = Path("studio/gui_entry.py").read_text(encoding="utf-8")
    assert "render_studio_style()" in shell
    assert shell.index("render_studio_style()") < shell.index("selected = st.sidebar.radio")


def test_story_studio_no_longer_owns_duplicate_theme_css() -> None:
    content = Path("studio/story_studio.py").read_text(encoding="utf-8")
    assert "<style>" not in content


def test_metric_values_wrap_instead_of_showing_ellipsis() -> None:
    assert '[data-testid="stMetricValue"] *' in STUDIO_STYLE
    assert "font-size: clamp(" in STUDIO_STYLE
    assert "white-space: normal !important" in STUDIO_STYLE
    assert "text-overflow: clip !important" in STUDIO_STYLE
    assert "overflow-wrap: anywhere" in STUDIO_STYLE
    assert "-webkit-line-clamp: unset !important" in STUDIO_STYLE
    assert "max-width: none !important" in STUDIO_STYLE
