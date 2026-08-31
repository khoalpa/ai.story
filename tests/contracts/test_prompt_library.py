from __future__ import annotations

from pathlib import Path

from studio.prompt_library import (
    _select_prompt_page,
    discover_prompt_files,
    load_prompt,
    search_prompt,
)


def test_discovery_sorts_semantic_versions_newest_first(tmp_path: Path) -> None:
    for name in ("ChatGPT_prompt_v3.9.9.txt", "ChatGPT_prompt_v3.11.1.txt", "notes.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert [path.name for path in discover_prompt_files(tmp_path)] == [
        "ChatGPT_prompt_v3.11.1.txt",
        "ChatGPT_prompt_v3.9.9.txt",
    ]


def test_prompt_loader_parses_module_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "ChatGPT_prompt_v1.2.3.txt"
    path.write_text(
        "===== MODULE:HEADER BEGIN =====\nhello\n===== MODULE:HEADER END =====\n",
        encoding="utf-8",
    )
    document = load_prompt(path)
    assert document.version == (1, 2, 3)
    assert document.modules[0].name == "HEADER"
    assert document.modules[0].start_line == 1
    assert document.modules[0].end_line == 3


def test_search_returns_line_and_module(tmp_path: Path) -> None:
    path = tmp_path / "ChatGPT_prompt_v1.0.0.txt"
    path.write_text(
        "===== MODULE:RULES BEGIN =====\nSafety Gate\n===== MODULE:RULES END =====\n",
        encoding="utf-8",
    )
    results = search_prompt(load_prompt(path), "safety")
    assert results == [{"Dòng": 2, "Module": "RULES", "Nội dung": "Safety Gate"}]


def test_single_page_module_does_not_render_zero_range_slider() -> None:
    class StreamlitStub:
        def select_slider(self, *_args, **_kwargs):
            raise AssertionError("single-page module must not create a slider")

    assert _select_prompt_page(
        StreamlitStub(), page_count=1, version="v1.0.0", module="HEADER"
    ) == 1


def test_multi_page_module_uses_slider() -> None:
    class StreamlitStub:
        def select_slider(self, *_args, **kwargs):
            assert kwargs["options"] == [1, 2, 3]
            return 2

    assert _select_prompt_page(
        StreamlitStub(), page_count=3, version="v1.0.0", module="RUNTIME"
    ) == 2


def test_prompt_library_exposes_native_directory_picker() -> None:
    source = Path("studio/prompt_library.py").read_text(encoding="utf-8")

    assert "def choose_prompt_directory" in source
    assert "filedialog.askdirectory" in source
    assert 'key="prompt_library_choose_directory"' in source
    assert "on_click=choose_prompt_directory" in source
