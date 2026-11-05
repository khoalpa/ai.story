from __future__ import annotations

from pathlib import Path

import pytest

from studio.prompt_contract import (
    PROJECT_ROOT,
    SUPPORTED_PROMPT_FILENAME,
    SUPPORTED_PROMPT_FILENAMES,
)
from studio.prompt_library import (
    _select_prompt_page,
    discover_prompt_files,
    inspect_reference_packages,
    load_prompt,
    search_prompt,
)
from studio.reference_samples import get_reference_dataset

PROMPT = PROJECT_ROOT / "prompts" / SUPPORTED_PROMPT_FILENAME


def test_discovery_returns_all_supported_prompts(tmp_path: Path) -> None:
    for name in (*SUPPORTED_PROMPT_FILENAMES, "ChatGPT_prompt_v3.16.13.txt", "notes.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert discover_prompt_files(tmp_path) == [tmp_path / name for name in SUPPORTED_PROMPT_FILENAMES]


def test_prompt_loader_parses_v522_numbered_sections() -> None:
    document = load_prompt(PROMPT)

    assert document.version == (5, 2, 2)
    assert document.modules[0].name == "0."
    assert document.modules[0].title == "PHẠM VI VÀ CÁCH DÙNG"
    assert any(module.name == "21." for module in document.modules)
    assert any(module.name == "28." for module in document.modules)


def test_v522_routes_attached_series_anchor_to_next_episode() -> None:
    prompt = PROMPT.read_text(encoding="utf-8")
    quickstart = PROMPT.with_name("ChatGPT_prompt_v5.2.2_Quickstart.txt").read_text(encoding="utf-8")

    required_rules = (
        "kiểm kê tên và loại các tệp đính kèm",
        "Tự xác định profile=`SERIAL_DETECTIVE`",
        "operation=CREATE_NEXT và tạo tập N+1",
        "last_completed_episode=0` → operation=START, tạo tập 1",
        "không âm thầm chuyển sang ADULT_STANDARD/standalone",
        "T56 —", "T57 —", "T58 —", "T59 —", "T60 —",
    )
    assert all(rule in prompt for rule in required_rules)
    assert "3. Trinh thám nhiều tập" in prompt
    assert "Các T01–T60" in prompt
    assert "SERIAL_DETECTIVE" in quickstart
    assert "CREATE_NEXT tập N+1" in quickstart
    assert "Revision: r3" in quickstart


def test_prompt_loader_rejects_old_or_renamed_prompt(tmp_path: Path) -> None:
    old = tmp_path / "ChatGPT_prompt_v3.16.13.txt"
    old.write_text(PROMPT.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="Chỉ hỗ trợ"):
        load_prompt(old)


def test_search_returns_line_and_numbered_section() -> None:
    results = search_prompt(load_prompt(PROMPT), "CHARACTER IMAGE PACK")

    assert results
    assert results[0]["Dòng"] > 1
    assert "character image pack" in str(results[0]["Nội dung"]).casefold()


def test_selected_reference_dataset_is_inspected() -> None:
    dataset = get_reference_dataset()
    rows = inspect_reference_packages(dataset=dataset)

    assert rows
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
