"""Browse and compare versioned ChatGPT prompt text files."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, MutableMapping

from studio.project_context import existing_picker_directory
from studio.prompt_contract import PROMPT_FILENAME as PROMPT_PATTERN

MODULE_BEGIN = re.compile(r"^===== MODULE:([^ ]+) BEGIN =====$")
MODULE_END = re.compile(r"^===== MODULE:([^ ]+) END =====$")
MAX_PROMPT_BYTES = 5 * 1024 * 1024
PAGE_SIZE = 200
PROMPT_LIBRARY_DIRECTORY_KEY = "prompt_library_directory"
PROMPT_LIBRARY_DIRECTORY_ERROR_KEY = "prompt_library_directory_error"


def choose_prompt_directory(state: MutableMapping[str, Any]) -> str | None:
    """Open the native folder picker for the prompt library directory."""
    root = None
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=root,
            initialdir=existing_picker_directory(
                str(state.get(PROMPT_LIBRARY_DIRECTORY_KEY) or "")
            ),
            mustexist=True,
            title="Chọn thư mục prompt",
        )
        if selected:
            value = str(Path(selected).expanduser().resolve())
            state[PROMPT_LIBRARY_DIRECTORY_KEY] = value
            state.pop(PROMPT_LIBRARY_DIRECTORY_ERROR_KEY, None)
            return value
        state.pop(PROMPT_LIBRARY_DIRECTORY_ERROR_KEY, None)
        return None
    except Exception as exc:
        state[PROMPT_LIBRARY_DIRECTORY_ERROR_KEY] = (
            f"Không thể mở hộp thoại chọn thư mục: {exc}"
        )
        return None
    finally:
        if root is not None:
            root.destroy()


@dataclass(frozen=True)
class PromptModule:
    name: str
    start_line: int
    end_line: int

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


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
    if not directory.is_dir():
        return []
    candidates = [path for path in directory.iterdir() if path.is_file() and PROMPT_PATTERN.match(path.name)]
    return sorted(candidates, key=lambda path: _version_from_name(path.name), reverse=True)


def _version_from_name(filename: str) -> tuple[int, int, int]:
    match = PROMPT_PATTERN.match(filename)
    if not match:
        raise ValueError(f"Tên tệp không đúng mẫu ChatGPT_prompt_v*.*.*.txt: {filename}")
    return tuple(int(value) for value in match.groups())  # type: ignore[return-value]


def _parse_modules(lines: tuple[str, ...]) -> tuple[PromptModule, ...]:
    open_modules: dict[str, int] = {}
    modules: list[PromptModule] = []
    for line_number, line in enumerate(lines, start=1):
        begin = MODULE_BEGIN.match(line.strip())
        if begin:
            open_modules[begin.group(1)] = line_number
            continue
        end = MODULE_END.match(line.strip())
        if end and end.group(1) in open_modules:
            name = end.group(1)
            modules.append(PromptModule(name, open_modules.pop(name), line_number))
    for name, start_line in open_modules.items():
        modules.append(PromptModule(name, start_line, len(lines)))
    if not modules and lines:
        modules.append(PromptModule("DOCUMENT", 1, len(lines)))
    return tuple(sorted(modules, key=lambda item: item.start_line))


def load_prompt(path: Path) -> PromptDocument:
    if not path.is_file():
        raise ValueError("Không tìm thấy tệp prompt.")
    if path.stat().st_size > MAX_PROMPT_BYTES:
        raise ValueError("Tệp prompt lớn hơn giới hạn 5 MB.")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Prompt không phải UTF-8 hợp lệ: {exc}") from exc
    lines = tuple(text.splitlines())
    return PromptDocument(path, _version_from_name(path.name), text, lines, _parse_modules(lines))


def search_prompt(document: PromptDocument, query: str, *, limit: int = 200) -> list[dict[str, object]]:
    needle = query.casefold().strip()
    if not needle:
        return []
    results: list[dict[str, object]] = []
    module_index = 0
    for line_number, line in enumerate(document.lines, start=1):
        while module_index + 1 < len(document.modules) and line_number > document.modules[module_index].end_line:
            module_index += 1
        if needle in line.casefold():
            module = document.modules[module_index].name if document.modules else "DOCUMENT"
            results.append({"Dòng": line_number, "Module": module, "Nội dung": line.strip()})
            if len(results) >= limit:
                break
    return results


def _module_text(document: PromptDocument, module: PromptModule) -> tuple[str, ...]:
    return document.lines[module.start_line - 1:module.end_line]


def _select_prompt_page(st: Any, *, page_count: int, version: str, module: str) -> int:
    """Avoid Streamlit's zero-range slider crash for single-page modules."""
    if page_count <= 1:
        return 1
    return int(st.select_slider(
        "Trang",
        options=list(range(1, page_count + 1)),
        value=1,
        format_func=lambda value: f"{value}/{page_count}",
        key=f"prompt_page_{version}_{module}",
    ))


def _render_document(document: PromptDocument) -> None:
    import streamlit as st

    query = st.text_input("Tìm trong phiên bản", key="prompt_library_search", placeholder="Nhập rule, gate hoặc từ khóa…")
    if query.strip():
        results = search_prompt(document, query)
        st.caption(f"{len(results)} kết quả đầu tiên" + (" (giới hạn 200)" if len(results) == 200 else ""))
        if results:
            st.dataframe(results, hide_index=True, use_container_width=True)
        else:
            st.info("Không tìm thấy nội dung phù hợp.")
        return

    module_names = [module.name for module in document.modules]
    selected_name = st.selectbox(
        "Module",
        module_names,
        key=f"prompt_module_{document.version_label}",
        format_func=lambda name: name.replace("_", " ").title(),
    )
    module = next(item for item in document.modules if item.name == selected_name)
    module_lines = _module_text(document, module)
    page_count = max(1, (len(module_lines) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = _select_prompt_page(
        st,
        page_count=page_count,
        version=document.version_label,
        module=module.name,
    )
    start = (page - 1) * PAGE_SIZE
    visible = module_lines[start:start + PAGE_SIZE]
    first_line = module.start_line + start
    last_line = first_line + len(visible) - 1
    st.caption(f"Dòng {first_line:,}–{last_line:,} · module có {module.line_count:,} dòng")
    numbered = "\n".join(f"{line_number:>5}  {line}" for line_number, line in enumerate(visible, start=first_line))
    st.code(numbered, language=None, line_numbers=False)


def _render_structure(document: PromptDocument) -> None:
    import streamlit as st

    word_count = len(document.text.split())
    columns = st.columns(4)
    columns[0].metric("Phiên bản", document.version_label)
    columns[1].metric("Module", len(document.modules))
    columns[2].metric("Số dòng", f"{len(document.lines):,}")
    columns[3].metric("Số từ", f"{word_count:,}")
    st.dataframe(
        [{
            "Module": module.name.replace("_", " ").title(),
            "Dòng bắt đầu": module.start_line,
            "Dòng kết thúc": module.end_line,
            "Số dòng": module.line_count,
        } for module in document.modules],
        hide_index=True,
        use_container_width=True,
    )


def _render_compare(documents: list[PromptDocument]) -> None:
    import streamlit as st

    if len(documents) < 2:
        st.info("Cần ít nhất hai tệp prompt để so sánh phiên bản.")
        return
    labels = [document.version_label for document in documents]
    left_col, right_col = st.columns(2)
    left_label = left_col.selectbox("Phiên bản gốc", labels, index=min(1, len(labels) - 1), key="prompt_compare_left")
    right_label = right_col.selectbox("Phiên bản mới", labels, index=0, key="prompt_compare_right")
    if left_label == right_label:
        st.info("Chọn hai phiên bản khác nhau để xem thay đổi.")
        return
    left = next(document for document in documents if document.version_label == left_label)
    right = next(document for document in documents if document.version_label == right_label)
    diff = list(difflib.unified_diff(left.lines, right.lines, fromfile=left.path.name, tofile=right.path.name, lineterm=""))
    added = sum(line.startswith("+") and not line.startswith("+++") for line in diff)
    removed = sum(line.startswith("-") and not line.startswith("---") for line in diff)
    cols = st.columns(3)
    cols[0].metric("Dòng thêm", added)
    cols[1].metric("Dòng xóa", removed)
    cols[2].metric("Tổng diff", len(diff))
    if not diff:
        st.success("Hai phiên bản có nội dung giống nhau.")
    else:
        limit = 2_000
        st.code("\n".join(diff[:limit]), language="diff")
        if len(diff) > limit:
            st.warning(f"Diff đã được rút gọn còn {limit:,}/{len(diff):,} dòng.")


def render_prompt_library_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Prompts", page_icon=":material/code_blocks:", layout="wide")
    st.header("Prompts")
    st.caption("Duyệt, tìm kiếm và so sánh các tệp ChatGPT_prompt_v*.*.*.txt theo module.")
    default_directory = str((Path.cwd() / "prompts").resolve())
    if PROMPT_LIBRARY_DIRECTORY_KEY not in st.session_state:
        st.session_state[PROMPT_LIBRARY_DIRECTORY_KEY] = default_directory
    directory_col, picker_col = st.columns([6, 1])
    directory_text = directory_col.text_input(
        "Thư mục prompt", key=PROMPT_LIBRARY_DIRECTORY_KEY,
    )
    picker_col.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
    picker_col.button(
        "Chọn thư mục",
        key="prompt_library_choose_directory",
        width="stretch",
        on_click=choose_prompt_directory,
        args=(st.session_state,),
    )
    if st.session_state.get(PROMPT_LIBRARY_DIRECTORY_ERROR_KEY):
        st.error(st.session_state[PROMPT_LIBRARY_DIRECTORY_ERROR_KEY])
    directory = Path(directory_text.strip()).expanduser()
    paths = discover_prompt_files(directory)
    if not paths:
        st.info("Không tìm thấy tệp ChatGPT_prompt_v*.*.*.txt trong thư mục đã chọn.")
        return
    documents: list[PromptDocument] = []
    errors: list[str] = []
    for path in paths:
        try:
            documents.append(load_prompt(path))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        st.warning("\n".join(errors))
    if not documents:
        return
    selected_label = st.selectbox(
        "Phiên bản",
        [document.version_label for document in documents],
        key="prompt_library_version",
    )
    selected = next(document for document in documents if document.version_label == selected_label)
    st.caption(f"`{selected.path.name}` · {selected.path.stat().st_size / 1024:.0f} KB")
    reader, structure, compare = st.tabs(["Đọc prompt", "Cấu trúc", "So sánh phiên bản"])
    with reader:
        _render_document(selected)
    with structure:
        _render_structure(selected)
    with compare:
        _render_compare(documents)


__all__ = [
    "PromptDocument",
    "PromptModule",
    "_select_prompt_page",
    "choose_prompt_directory",
    "discover_prompt_files",
    "load_prompt",
    "render_prompt_library_workspace",
    "search_prompt",
]
