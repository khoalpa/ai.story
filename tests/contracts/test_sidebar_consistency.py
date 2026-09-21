from __future__ import annotations

from pathlib import Path

from audio.gui.sidebar_sections import SIDEBAR_SECTION_ORDER as AUDIO_SIDEBAR_ORDER
from video.gui.sidebar_sections import SIDEBAR_SECTION_ORDER as VIDEO_SIDEBAR_ORDER
from video.gui.sidebar_sections import SidebarSection as VideoSidebarSection

SIDEBAR_SECTION_NAMES = (
    "INPUTS_OUTPUTS",
    "PROFILES",
    "PROVIDER",
    "GENERATION",
    "RENDER",
    "ADVANCED",
    "RUNTIME",
)


def test_sidebar_section_labels_are_shared_across_apps() -> None:
    expected_files = [
        Path("audio/gui/settings.py"),
        Path("video/gui/settings.py"),
    ]

    for path in expected_files:
        content = path.read_text(encoding="utf-8")
        assert "SidebarSection" in content


def test_sidebar_uses_consistent_section_vocabulary() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            Path("audio/gui/settings.py"),
            Path("video/gui/settings.py"),
        ]
    )

    assert 'st.header("LLM options")' not in combined
    assert 'st.header("Image provider")' not in combined
    assert 'st.header("Inputs / outputs")' not in combined
    assert 'st.header("Render options")' not in combined
    assert 'st.header("Input roots")' not in combined
    assert 'st.header("Output")' not in combined


def test_sidebar_sections_follow_shared_order() -> None:
    assert tuple(section.name for section in AUDIO_SIDEBAR_ORDER) == SIDEBAR_SECTION_NAMES
    assert tuple(section.name for section in VIDEO_SIDEBAR_ORDER) == SIDEBAR_SECTION_NAMES
    assert tuple(section.value for section in AUDIO_SIDEBAR_ORDER) == tuple(
        VideoSidebarSection[section.name].value for section in VIDEO_SIDEBAR_ORDER
    )

    for path in (Path("audio/gui/settings.py"), Path("video/gui/settings.py")):
        content = path.read_text(encoding="utf-8")
        assert "sidebar_slots = {section: st.empty() for section in SIDEBAR_SECTION_ORDER}" in content
        assert "sidebar_slots[SidebarSection.INPUTS_OUTPUTS]" in content
        assert "sidebar_slots[SidebarSection.PROVIDER]" in content
        assert "sidebar_slots[SidebarSection.RENDER]" in content
        assert "sidebar_slots[SidebarSection.ADVANCED]" in content
        assert "sidebar_slots[SidebarSection.RUNTIME]" in content


def test_video_runtime_diagnostics_replaces_runtime_wrapper() -> None:
    content = Path("video/gui/settings.py").read_text(encoding="utf-8")

    assert "with st.expander(SidebarSection.RUNTIME" not in content
    assert "render_runtime_diagnostics_block(report, expanded=False" in content


def test_audio_runtime_diagnostics_is_collapsed_by_default() -> None:
    content = Path("audio/gui/settings.py").read_text(encoding="utf-8")

    assert "_expander(SidebarSection.RUNTIME, expanded=False)" in content

