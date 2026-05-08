from __future__ import annotations

import re
from pathlib import Path


SIDEBAR_SECTION_ORDER = [
    "PROFILES",
    "PROVIDER",
    "INPUTS_OUTPUTS",
    "GENERATION",
    "RENDER",
    "ADVANCED",
    "RUNTIME",
]


def test_sidebar_section_labels_are_shared_across_apps() -> None:
    expected_files = [
        Path("story/gui/sidebar.py"),
        Path("audio/gui/settings.py"),
        Path("image/gui/settings.py"),
        Path("video/gui/settings.py"),
    ]

    for path in expected_files:
        content = path.read_text(encoding="utf-8")
        assert "SidebarSection" in content


def test_sidebar_uses_consistent_section_vocabulary() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            Path("story/gui/sidebar.py"),
            Path("audio/gui/settings.py"),
            Path("image/gui/settings.py"),
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
    expected_files = [
        Path("story/gui/sidebar.py"),
        Path("audio/gui/settings.py"),
        Path("image/gui/settings.py"),
        Path("video/gui/settings.py"),
    ]

    pattern = re.compile(r"st\.(?:header|expander)\(SidebarSection\.([A-Z_]+)")
    order_index = {section: index for index, section in enumerate(SIDEBAR_SECTION_ORDER)}

    for path in expected_files:
        sections = pattern.findall(path.read_text(encoding="utf-8"))
        first_seen_sections = list(dict.fromkeys(section for section in sections if section in order_index))
        indexed_sections = [order_index[section] for section in first_seen_sections]
        assert indexed_sections == sorted(indexed_sections), f"{path} sidebar sections are out of order: {sections}"

