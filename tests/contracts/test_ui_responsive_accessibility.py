from __future__ import annotations

from pathlib import Path

from studio.ui_style import STUDIO_STYLE


def test_responsive_contract_covers_tablet_and_compact_layouts() -> None:
    assert "@media (max-width: 1024px)" in STUDIO_STYLE
    assert "@media (max-width: 768px)" in STUDIO_STYLE
    assert "@media (max-width: 640px)" in STUDIO_STYLE
    assert ".studio-progress__list" in STUDIO_STYLE
    assert "overflow-x: auto" in STUDIO_STYLE


def test_accessibility_contract_keeps_focus_and_non_color_status_cues() -> None:
    assert ":focus-visible" in STUDIO_STYLE
    assert "outline:" in STUDIO_STYLE
    assert 'aria-label="Tiến độ sản xuất"' in Path("studio/ui_components.py").read_text(
        encoding="utf-8"
    )
    assert 'aria-current=' in Path("studio/ui_components.py").read_text(encoding="utf-8")


def test_primary_controls_meet_minimum_pointer_target() -> None:
    assert "--studio-control-min-height: 2.75rem" in STUDIO_STYLE
