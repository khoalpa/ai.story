from __future__ import annotations

from pathlib import Path

import pytest

from studio.prompt_contract import PROJECT_ROOT, SUPPORTED_PROMPT_FILENAME
from studio.prompt_library import (
    REFERENCE_PACKAGE_DIRECTORY,
    REFERENCE_PACKAGE_NAMES,
    _select_prompt_page,
    discover_prompt_files,
    inspect_reference_packages,
    load_prompt,
    search_prompt,
)

PROMPT = PROJECT_ROOT / "prompts" / SUPPORTED_PROMPT_FILENAME


def test_discovery_returns_only_supported_prompt(tmp_path: Path) -> None:
    for name in (SUPPORTED_PROMPT_FILENAME, "ChatGPT_prompt_v3.16.13.txt", "notes.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert discover_prompt_files(tmp_path) == [tmp_path / SUPPORTED_PROMPT_FILENAME]


def test_prompt_loader_parses_v416_numbered_sections() -> None:
    document = load_prompt(PROMPT)

    assert document.version == (4, 1, 6)
    assert document.modules[0].name == "0."
    assert document.modules[0].title == "PHẠM VI VÀ CÁCH DÙNG"
    assert any(module.name == "11.1." for module in document.modules)


def test_prompt_loader_rejects_old_or_renamed_prompt(tmp_path: Path) -> None:
    old = tmp_path / "ChatGPT_prompt_v3.16.13.txt"
    old.write_text(PROMPT.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="Chỉ hỗ trợ"):
        load_prompt(old)


def test_search_returns_line_and_numbered_section() -> None:
    results = search_prompt(load_prompt(PROMPT), "KHÔI PHỤC ZIP")

    assert results
    assert str(results[0]["Mục"]).startswith("11.1.")
    assert "KHÔI PHỤC ZIP" in str(results[0]["Nội dung"])


def test_reference_packages_are_exact_v416_examples(sample_archives_dir: Path) -> None:
    assert REFERENCE_PACKAGE_DIRECTORY == sample_archives_dir
    rows = inspect_reference_packages()

    assert tuple(row["Gói"] for row in rows) == REFERENCE_PACKAGE_NAMES
    assert [row["Giai đoạn"] for row in rows] == ["STAGE1", "STAGE2", "STAGE3", "STAGE4"]
    assert all(row["Trạng thái"] == "PASS" for row in rows)
    assert all(row["Tương thích"] == "NATIVE_CURRENT" for row in rows)


def test_single_page_module_does_not_render_zero_range_slider() -> None:
    class StreamlitStub:
        def select_slider(self, *_args, **_kwargs):
            raise AssertionError("single-page module must not create a slider")

    assert _select_prompt_page(
        StreamlitStub(), page_count=1, version="v4.1.6", module="0."
    ) == 1


def test_multi_page_module_uses_slider() -> None:
    class StreamlitStub:
        def select_slider(self, *_args, **kwargs):
            assert kwargs["options"] == [1, 2, 3]
            return 2

    assert _select_prompt_page(
        StreamlitStub(), page_count=3, version="v4.1.6", module="10."
    ) == 2


def test_prompt_library_has_no_old_version_picker_or_compare_view() -> None:
    source = Path("studio/prompt_library.py").read_text(encoding="utf-8")

    assert "choose_prompt_directory" not in source
    assert "So sánh phiên bản" not in source
    assert "difflib" not in source
    assert "SUPPORTED_PROMPT_FILENAME" in source
