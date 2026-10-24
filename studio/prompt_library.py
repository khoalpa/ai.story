"""Read the canonical v4.1.6 prompt and its shipped reference packages.

This workspace is deliberately single-version. It does not discover, compare,
upgrade, or provide a compatibility view for older prompt/package versions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from studio.prompt_contract import (
    PROJECT_ROOT,
    SUPPORTED_PROMPT_FILENAME,
    SUPPORTED_PROMPT_VERSION,
    load_prompt_contract,
)
from studio.reference_samples import (
    REFERENCE_PACKAGE_DIRECTORY,
    REFERENCE_PACKAGE_NAMES,
    load_reference_package,
)
from studio.workflow_package import inspect_directory

MAX_PROMPT_BYTES = 5 * 1024 * 1024
PAGE_SIZE = 200
SECTION_HEADING = re.compile(r"^(\d+(?:\.\d+)*\.)\s+(.+?)\s*$")


@dataclass(frozen=True)
class PromptModule:
    """A numbered section in the prose-first v4.1.6 contract."""

    name: str
    start_line: int
    end_line: int
    title: str = ""

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    @property
    def label(self) -> str:
        return f"{self.name} {self.title}".strip()


@dataclass(frozen=True)
class PromptDocument:
    path: Path
    version: tuple[int, int, int]
    text: str
    lines: tuple[str, ...]
    modules: tuple[PromptModule, ...]

    @property
    def version_label(self) -> str:
        return "v" + ".".join(str(value) for value in self.version)


def discover_prompt_files(directory: Path) -> list[Path]:
    """Return only the one prompt contract supported by this application."""
    path = directory / SUPPORTED_PROMPT_FILENAME
    return [path] if path.is_file() else []


def _parse_modules(lines: tuple[str, ...]) -> tuple[PromptModule, ...]:
    headings: list[tuple[str, str, int]] = []
    for line_number, line in enumerate(lines, start=1):
        match = SECTION_HEADING.match(line.strip())
        # Contract headings are uppercase; numbered workflow/list items are not.
        # This distinction comes from v4.1.6's real prose structure rather than
        # reusing the MODULE sentinels of older prompt generations.
        if match and match.group(2) == match.group(2).upper():
            headings.append((match.group(1), match.group(2), line_number))
    if not headings:
        return (PromptModule("DOCUMENT", 1, len(lines), "Toàn bộ hợp đồng"),) if lines else ()
    modules: list[PromptModule] = []
    for index, (number, title, start_line) in enumerate(headings):
        end_line = headings[index + 1][2] - 1 if index + 1 < len(headings) else len(lines)
        modules.append(PromptModule(number, start_line, end_line, title))
    return tuple(modules)


def load_prompt(path: Path) -> PromptDocument:
    """Load the exact canonical prompt; similarly named old prompts are rejected."""
    if path.name != SUPPORTED_PROMPT_FILENAME:
        raise ValueError(f"Chỉ hỗ trợ {SUPPORTED_PROMPT_FILENAME}.")
    if not path.is_file():
        raise ValueError("Không tìm thấy tệp prompt v4.1.6.")
    if path.stat().st_size > MAX_PROMPT_BYTES:
        raise ValueError("Tệp prompt lớn hơn giới hạn 5 MB.")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Prompt không phải UTF-8 hợp lệ: {exc}") from exc
    if not text.startswith("CHATGPT AUDIO STORY PACKAGE — v4.1.6"):
        raise ValueError("Nội dung không phải hợp đồng prompt v4.1.6.")
    lines = tuple(text.splitlines())
    return PromptDocument(path, SUPPORTED_PROMPT_VERSION, text, lines, _parse_modules(lines))


def search_prompt(document: PromptDocument, query: str, *, limit: int = 200) -> list[dict[str, object]]:
    needle = query.casefold().strip()
    if not needle:
        return []
    results: list[dict[str, object]] = []
    module_index = 0
    for line_number, line in enumerate(document.lines, start=1):
        while (
            module_index + 1 < len(document.modules)
            and line_number > document.modules[module_index].end_line
        ):
            module_index += 1
        if needle in line.casefold():
            module = document.modules[module_index].label if document.modules else "DOCUMENT"
            results.append({"Dòng": line_number, "Mục": module, "Nội dung": line.strip()})
            if len(results) >= limit:
                break
    return results


def _module_text(document: PromptDocument, module: PromptModule) -> tuple[str, ...]:
    return document.lines[module.start_line - 1 : module.end_line]


def _select_prompt_page(st: Any, *, page_count: int, version: str, module: str) -> int:
    if page_count <= 1:
        return 1
    return int(
        st.select_slider(
            "Trang",
            options=list(range(1, page_count + 1)),
            value=1,
            format_func=lambda value: f"{value}/{page_count}",
            key=f"prompt_page_{version}_{module}",
        )
    )


def _first_failure(result: Mapping[str, Any]) -> str:
    for row in result.get("checks", []):
        if row.get("status") != "PASS":
            return str(row.get("detail") or row.get("check") or "Kiểm tra thất bại")
    return ""


def inspect_reference_packages(
    templates_directory: Path = REFERENCE_PACKAGE_DIRECTORY,
) -> list[dict[str, object]]:
    """Inspect the four v4.1.6 example archives with the production validator."""
    rows: list[dict[str, object]] = []
    for package_name in REFERENCE_PACKAGE_NAMES:
        try:
            members, result = load_reference_package(package_name, templates_directory)
            failed = sum(row.get("status") != "PASS" for row in result.get("checks", []))
            rows.append(
                {
                    "Gói": package_name,
                    "Giai đoạn": result.get("stage") or "—",
                    "Trạng thái": result.get("status", "FAIL"),
                    "Tương thích": result.get("compatibility", "UNSUPPORTED"),
                    "Số tệp": len(members),
                    "Kiểm tra lỗi": failed,
                    "Chi tiết": "" if result.get("status") == "PASS" else _first_failure(result),
                }
            )
        except (OSError, ValueError) as exc:
            rows.append(
                {
                    "Gói": package_name,
                    "Giai đoạn": "—",
                    "Trạng thái": "FAIL",
                    "Tương thích": "UNSUPPORTED",
                    "Số tệp": 0,
                    "Kiểm tra lỗi": 1,
                    "Chi tiết": str(exc),
                }
            )
    return rows


def _render_document(document: PromptDocument) -> None:
    import streamlit as st

    query = st.text_input(
        "Tìm trong prompt v4.1.6",
        key="prompt_library_search",
        placeholder="Nhập quy tắc, gate hoặc từ khóa…",
    )
    if query.strip():
        results = search_prompt(document, query)
        st.caption(f"{len(results)} kết quả đầu tiên" + (" (giới hạn 200)" if len(results) == 200 else ""))
        if results:
            st.dataframe(results, hide_index=True, width="stretch")
        else:
            st.info("Không tìm thấy nội dung phù hợp.")
        return

    selected_label = st.selectbox(
        "Mục",
        [module.label for module in document.modules],
        key="prompt_module_v4.1.6",
    )
    module = next(item for item in document.modules if item.label == selected_label)
    module_lines = _module_text(document, module)
    page_count = max(1, (len(module_lines) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = _select_prompt_page(st, page_count=page_count, version=document.version_label, module=module.name)
    start = (page - 1) * PAGE_SIZE
    visible = module_lines[start : start + PAGE_SIZE]
    first_line = module.start_line + start
    last_line = first_line + len(visible) - 1
    st.caption(f"Dòng {first_line:,}–{last_line:,} · mục có {module.line_count:,} dòng")
    numbered = "\n".join(
        f"{line_number:>5}  {line}" for line_number, line in enumerate(visible, start=first_line)
    )
    st.code(numbered, language=None, line_numbers=False)


def _render_structure(document: PromptDocument) -> None:
    import streamlit as st

    contract = load_prompt_contract(document.path)
    columns = st.columns(4)
    columns[0].metric("Prompt", document.version_label)
    columns[1].metric("Schema dữ liệu", contract.story_schema_version or "—")
    columns[2].metric("Mục", len(document.modules))
    columns[3].metric("Số dòng", f"{len(document.lines):,}")
    st.caption("Prompt 4.1.6 và schema 4.1.3 là hai định danh độc lập; ứng dụng không chuyển đổi bằng thay chuỗi version.")
    st.dataframe(
        [
            {
                "Mục": module.name,
                "Tiêu đề": module.title,
                "Dòng bắt đầu": module.start_line,
                "Dòng kết thúc": module.end_line,
                "Số dòng": module.line_count,
            }
            for module in document.modules
        ],
        hide_index=True,
        width="stretch",
    )


def _render_reference_packages() -> None:
    import streamlit as st

    st.caption("Bốn ZIP phát hành cùng prompt được mở trong bộ nhớ và kiểm bằng hợp đồng v4.1.6 hiện hành.")
    rows = inspect_reference_packages()
    st.dataframe(rows, hide_index=True, width="stretch")
    if rows and all(
        row["Trạng thái"] == "PASS" and row["Tương thích"] == "NATIVE_CURRENT"
        for row in rows
    ):
        st.success("Cả bốn ZIP mẫu đều đạt kiểm tra v4.1.6.")
    else:
        st.error("Có ZIP mẫu thiếu, hỏng hoặc không đúng hợp đồng v4.1.6.")


def _render_reference_story(output_directory: Path | None = None) -> None:
    import streamlit as st

    if output_directory is None:
        try:
            _members, result = load_reference_package("story_video_prompts.zip")
        except (OSError, ValueError) as exc:
            st.error(str(exc))
            return
        st.caption("Truyện tham khảo được đọc từ ZIP mẫu Stage 4 đã xác minh checksum.")
    else:
        result = inspect_directory(output_directory)
    columns = st.columns(4)
    columns[0].metric("Giai đoạn", result.get("stage") or "—")
    columns[1].metric("Trạng thái", result.get("status") or "FAIL")
    columns[2].metric("Tệp payload", len(result.get("files", [])))
    columns[3].metric("Khả năng xuất bản", result.get("publish_status") or "FAIL")
    if result.get("compatibility") != "NATIVE_CURRENT":
        st.error("UNSUPPORTED: thư mục không phải gói v4.1.6; không có chế độ tương thích gói cũ.")
    elif result.get("status") == "PASS":
        st.success("Gói truyện mẫu khớp hợp đồng v4.1.6 và manifest.")
    else:
        st.error(_first_failure(result) or "Gói truyện mẫu không đạt kiểm tra.")
    st.dataframe(result.get("checks", []), hide_index=True, width="stretch")
    with st.expander("Manifest mẫu"):
        st.json(result.get("manifest", {}), expanded=False)


def render_prompt_library_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Thông tin prompt", page_icon=":material/code_blocks:", layout="wide")
    st.header("Thông tin prompt")
    st.caption("Hợp đồng duy nhất đang được hỗ trợ: prompt v4.1.6, schema dữ liệu v4.1.3.")
    prompt_path = PROJECT_ROOT / "prompts" / SUPPORTED_PROMPT_FILENAME
    try:
        document = load_prompt(prompt_path)
        contract = load_prompt_contract(prompt_path)
    except (OSError, UnicodeError, ValueError) as exc:
        st.error(f"Không nạp được hợp đồng v4.1.6: {exc}")
        return
    st.caption(f"`{document.path.name}` · SHA-256 `{contract.sha256}`")
    reader, structure, packages, story = st.tabs(
        ["Đọc prompt", "Cấu trúc v4.1.6", "ZIP mẫu", "Gói truyện mẫu"]
    )
    with reader:
        _render_document(document)
    with structure:
        _render_structure(document)
    with packages:
        _render_reference_packages()
    with story:
        _render_reference_story()


__all__ = [
    "PromptDocument",
    "PromptModule",
    "REFERENCE_PACKAGE_NAMES",
    "_select_prompt_page",
    "discover_prompt_files",
    "inspect_reference_packages",
    "load_prompt",
    "render_prompt_library_workspace",
    "search_prompt",
]
