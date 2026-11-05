"""Read supported v4 prompt contracts and their reference packages."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from studio.prompt_contract import (
    PROJECT_ROOT,
    SUPPORTED_PROMPT_FILENAMES,
    load_prompt_contract,
)
from studio.reference_samples import (
    REFERENCE_PACKAGE_DIRECTORY,
    REFERENCE_PACKAGE_NAMES,
    ReferenceDataset,
    get_reference_dataset,
    load_dataset_package,
    load_reference_package,
    load_reference_registry_tolerant,
)
from studio.ui_components import (
    render_empty_state,
    render_summary_card,
    render_workspace_header,
    status_badge_html,
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
    """Return supported prompt contracts in version order."""
    return [directory / name for name in SUPPORTED_PROMPT_FILENAMES if (directory / name).is_file()]


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
    """Load an exact supported canonical prompt."""
    if path.name not in SUPPORTED_PROMPT_FILENAMES:
        raise ValueError(f"Chỉ hỗ trợ {', '.join(SUPPORTED_PROMPT_FILENAMES)}.")
    if not path.is_file():
        raise ValueError("Không tìm thấy tệp prompt được hỗ trợ.")
    if path.stat().st_size > MAX_PROMPT_BYTES:
        raise ValueError("Tệp prompt lớn hơn giới hạn 5 MB.")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Prompt không phải UTF-8 hợp lệ: {exc}") from exc
    major, minor, patch = (int(part) for part in path.stem.removeprefix("ChatGPT_prompt_v").split("."))
    version = (major, minor, patch)
    version_label = ".".join(map(str, version))
    if not text.startswith(f"CHATGPT AUDIO STORY PACKAGE — v{version_label}"):
        raise ValueError(f"Nội dung không phải hợp đồng prompt v{version_label}.")
    lines = tuple(text.splitlines())
    return PromptDocument(path, version, text, lines, _parse_modules(lines))


def search_prompt(document: PromptDocument, query: str, *, limit: int = 200) -> list[dict[str, str | int]]:
    needle = query.casefold().strip()
    if not needle:
        return []
    results: list[dict[str, str | int]] = []
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
    dataset: ReferenceDataset | None = None,
) -> list[dict[str, str | int]]:
    """Inspect a selected dataset, retaining the legacy directory argument."""
    rows: list[dict[str, str | int]] = []
    packages = (
        tuple(dataset.packages.items())
        if dataset is not None
        else tuple((stage, name) for name, stage in zip(REFERENCE_PACKAGE_NAMES, ("STAGE1", "STAGE2", "STAGE3", "STAGE4")))
    )
    for stage, package_name in packages:
        try:
            members, result = (
                load_dataset_package(dataset, stage)
                if dataset is not None
                else load_reference_package(package_name, templates_directory)
            )
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
    if dataset is not None and dataset.project_directory is not None:
        result = inspect_directory(dataset.directory / dataset.project_directory)
        rows.append(
            {
                "Gói": "Project đã giải nén",
                "Giai đoạn": result.get("stage") or "—",
                "Trạng thái": result.get("status", "FAIL"),
                "Tương thích": result.get("compatibility", "UNSUPPORTED"),
                "Số tệp": len(result.get("files", [])),
                "Kiểm tra lỗi": sum(row.get("status") != "PASS" for row in result.get("checks", [])),
                "Chi tiết": "" if result.get("status") == "PASS" else _first_failure(result),
            }
        )
    return rows


def _render_document(document: PromptDocument) -> None:
    import streamlit as st

    module_key = f"prompt_module_{document.version_label}"
    page_key = f"prompt_reader_page_{document.version_label}"
    labels = [module.label for module in document.modules]
    if st.session_state.get(module_key) not in labels:
        st.session_state[module_key] = labels[0]

    navigation, reader = st.columns([1, 3], gap="large")
    with navigation:
        st.markdown("#### Mục lục")
        selected_label = st.selectbox(
            "Chọn mục",
            labels,
            key=module_key,
            label_visibility="collapsed",
        )
        st.caption(f"{len(document.modules)} mục · {len(document.lines):,} dòng")
        show_line_numbers = st.toggle(
            "Hiện số dòng", value=True, key=f"prompt_line_numbers_{document.version_label}"
        )

    module = next(item for item in document.modules if item.label == selected_label)
    module_lines = _module_text(document, module)
    page_count = max(1, (len(module_lines) + PAGE_SIZE - 1) // PAGE_SIZE)
    current_page = int(st.session_state.get(page_key, 1))
    current_page = max(1, min(page_count, current_page))
    st.session_state[page_key] = current_page

    with reader:
        query = st.text_input(
            f"Tìm trong prompt {document.version_label}",
            key="prompt_library_search",
            placeholder="Nhập quy tắc, gate hoặc từ khóa…",
        )
        if query.strip():
            results = search_prompt(document, query)
            st.caption(
                f"{len(results)} kết quả đầu tiên"
                + (" (giới hạn 200)" if len(results) == 200 else "")
            )
            if not results:
                render_empty_state(
                    "Không tìm thấy kết quả",
                    "Thử một từ khóa ngắn hơn hoặc kiểm tra lại cách viết.",
                    icon="⌕",
                )
                return

            def open_search_result(result_module: str, line_number: int) -> None:
                target = next(item for item in document.modules if item.label == result_module)
                st.session_state[module_key] = result_module
                st.session_state[page_key] = max(
                    1, (line_number - target.start_line) // PAGE_SIZE + 1
                )
                st.session_state["prompt_library_search"] = ""

            for index, result in enumerate(results[:30]):
                result_module = str(result["Mục"])
                line_number = int(result["Dòng"])
                with st.container(border=True):
                    meta, action = st.columns([5, 1])
                    meta.caption(f"{result_module} · dòng {line_number:,}")
                    meta.write(str(result["Nội dung"]) or "—")
                    action.button(
                        "Đi đến",
                        key=f"prompt_search_go_{index}_{line_number}",
                        width="stretch",
                        on_click=open_search_result,
                        args=(result_module, line_number),
                    )
            if len(results) > 30:
                st.caption(f"Còn {len(results) - 30} kết quả; hãy thu hẹp từ khóa để xem chính xác hơn.")
            return

        st.markdown(f"#### {module.label}")
        start = (current_page - 1) * PAGE_SIZE
        visible = module_lines[start : start + PAGE_SIZE]
        first_line = module.start_line + start
        last_line = first_line + len(visible) - 1
        st.caption(f"Dòng {first_line:,}–{last_line:,} · mục có {module.line_count:,} dòng")
        if show_line_numbers:
            visible_text = "\n".join(
                f"{line_number:>5}  {line}"
                for line_number, line in enumerate(visible, start=first_line)
            )
        else:
            visible_text = "\n".join(visible)
        st.code(visible_text, language=None, line_numbers=False)

        if page_count > 1:
            previous, page_status, following = st.columns([1, 2, 1])
            if previous.button(
                "← Trang trước",
                disabled=current_page <= 1,
                key=f"prompt_previous_{document.version_label}_{module.name}",
                width="stretch",
            ):
                st.session_state[page_key] = current_page - 1
                st.rerun()
            page_status.markdown(
                f"<div style='text-align:center;padding:.55rem'>Trang {current_page}/{page_count}</div>",
                unsafe_allow_html=True,
            )
            if following.button(
                "Trang sau →",
                disabled=current_page >= page_count,
                key=f"prompt_next_{document.version_label}_{module.name}",
                width="stretch",
            ):
                st.session_state[page_key] = current_page + 1
                st.rerun()


def _render_structure(document: PromptDocument) -> None:
    import streamlit as st

    contract = load_prompt_contract(document.path)
    columns = st.columns(4)
    with columns[0]:
        render_summary_card("Phiên bản prompt", document.version_label, detail="Hợp đồng sáng tác")
    with columns[1]:
        render_summary_card("Schema dữ liệu", contract.story_schema_version or "—", detail="Cấu trúc package")
    with columns[2]:
        render_summary_card("Số mục", len(document.modules), detail="Mục được đánh số")
    with columns[3]:
        render_summary_card("Tổng số dòng", f"{len(document.lines):,}", detail="Tài liệu UTF-8")
    cip = " · Character Image Pack 1.0" if contract.supports_character_image_pack else ""
    st.info(
        "Phiên bản prompt mô tả quy trình sáng tác; phiên bản schema mô tả cấu trúc dữ liệu. "
        f"Hai phiên bản này không nhất thiết giống nhau{cip}."
    )
    st.markdown("#### Cấu trúc tài liệu")
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


def _render_reference_packages(dataset: ReferenceDataset) -> None:
    import streamlit as st

    st.caption(f"Đang kiểm tra bộ `{dataset.set_id}` dành cho prompt {dataset.prompt_version}.")
    rows = inspect_reference_packages(dataset=dataset)
    passed = sum(row["Trạng thái"] == "PASS" for row in rows)
    compatible = sum(row["Tương thích"] == "NATIVE_CURRENT" for row in rows)
    summary = st.columns(3)
    summary[0].metric("Gói hợp lệ", f"{passed}/{len(rows)}")
    summary[1].metric("Đúng phiên bản", f"{compatible}/{len(rows)}")
    summary[2].metric("Lỗi phát hiện", sum(int(row["Kiểm tra lỗi"]) for row in rows))
    all_valid = bool(rows) and all(
        row["Trạng thái"] == "PASS" and row["Tương thích"] == "NATIVE_CURRENT"
        for row in rows
    )
    if all_valid:
        st.success(f"✓ Bộ dữ liệu tham chiếu đạt kiểm tra prompt {dataset.prompt_version}.")
    else:
        st.error("× Có package thiếu, hỏng hoặc không đúng hợp đồng của bộ mẫu.")
    for row in rows:
        valid = row["Trạng thái"] == "PASS"
        title = f"{'✓' if valid else '×'} {row['Giai đoạn']} · {row['Gói']}"
        with st.expander(title, expanded=not valid):
            left, middle, right = st.columns(3)
            left.metric("Trạng thái", "Hợp lệ" if valid else "Không đạt")
            middle.metric(
                "Tương thích",
                "Đúng phiên bản" if row["Tương thích"] == "NATIVE_CURRENT" else "Không được hỗ trợ",
            )
            right.metric("Số tệp", row["Số tệp"])
            if row["Chi tiết"]:
                st.error(str(row["Chi tiết"]))
            st.caption("Chi tiết kiểm tra")
            st.json(row, expanded=False)


def _render_reference_story(
    output_directory: Path | None = None, dataset: ReferenceDataset | None = None,
) -> None:
    import streamlit as st

    if output_directory is None:
        try:
            selected = dataset or get_reference_dataset()
            if selected.project_directory is not None:
                result = inspect_directory(selected.directory / selected.project_directory)
            else:
                _members, result = load_dataset_package(selected, "STAGE4")
        except (OSError, ValueError) as exc:
            st.error(str(exc))
            return
        st.caption(f"Truyện tham khảo được đọc từ bộ `{selected.set_id}`.")
    else:
        result = inspect_directory(output_directory)
    columns = st.columns(4)
    columns[0].metric("Giai đoạn", result.get("stage") or "—")
    columns[1].metric("Trạng thái", result.get("status") or "FAIL")
    columns[2].metric("Tệp payload", len(result.get("files", [])))
    columns[3].metric("Khả năng xuất bản", result.get("publish_status") or "FAIL")
    if result.get("compatibility") != "NATIVE_CURRENT":
        st.error("× Thư mục không đúng phiên bản prompt hiện tại; chỉ có thể xem ở chế độ tương thích.")
    elif result.get("status") == "PASS":
        st.success("✓ Gói truyện mẫu khớp hợp đồng prompt và manifest.")
    else:
        st.error(_first_failure(result) or "Gói truyện mẫu không đạt kiểm tra.")
    st.dataframe(result.get("checks", []), hide_index=True, width="stretch")
    with st.expander("Manifest mẫu"):
        st.json(result.get("manifest", {}), expanded=False)


def render_prompt_library_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Thông tin prompt", page_icon=":material/code_blocks:", layout="wide")
    prompt_paths = discover_prompt_files(PROJECT_ROOT / "prompts")
    if not prompt_paths:
        render_workspace_header(
            "Thông tin prompt",
            "Đọc hợp đồng, tra cứu quy tắc và kiểm chứng dữ liệu tham chiếu.",
            eyebrow="Tài liệu & kiểm chứng",
            status="Không có dữ liệu",
            status_tone="error",
        )
        render_empty_state(
            "Chưa tìm thấy prompt",
            "Hãy thêm một tệp prompt được hỗ trợ vào thư mục prompts.",
            icon="!",
        )
        return

    version_names = [path.name for path in reversed(prompt_paths)]
    selected_name = str(st.session_state.get("prompt_library_version") or version_names[0])
    if selected_name not in version_names:
        selected_name = version_names[0]
        st.session_state["prompt_library_version"] = selected_name
    prompt_path = next(path for path in prompt_paths if path.name == selected_name)
    try:
        document = load_prompt(prompt_path)
        contract = load_prompt_contract(prompt_path)
    except (OSError, UnicodeError, ValueError) as exc:
        st.error(f"Không nạp được hợp đồng prompt: {exc}")
        return

    legacy = document.version != max(load_prompt(path).version for path in prompt_paths)
    render_workspace_header(
        "Thông tin prompt",
        "Đọc hợp đồng, tra cứu quy tắc và kiểm chứng dữ liệu tham chiếu.",
        eyebrow="Tài liệu & kiểm chứng",
        status=f"{'Chỉ đọc' if legacy else 'Đang dùng'} · {document.version_label}",
        status_tone="warning" if legacy else "success",
    )

    context = st.container(border=True)
    with context:
        version_column, status_column, schema_column = st.columns([2, 1, 1])
        with version_column:
            selected_name = st.selectbox(
                "Phiên bản prompt",
                version_names,
                key="prompt_library_version",
            )
        with status_column:
            st.markdown("**Trạng thái**")
            st.html(
                status_badge_html(
                    "Chỉ đọc · bản cũ" if legacy else "Đang dùng",
                    tone="warning" if legacy else "success",
                )
            )
        with schema_column:
            st.markdown("**Schema dữ liệu**")
            st.write(contract.story_schema_version or "—")

        with st.expander("Chi tiết kỹ thuật"):
            st.code(str(document.path), language=None)
            st.caption(f"Tên tệp: `{document.path.name}`")
            st.caption(f"SHA-256: `{contract.sha256}`")

    if document.version in {(5, 0, 0), (5, 1, 0)}:
        st.warning(
            "Prompt này là bản chuyển tiếp đã ngừng dùng cho authoring mới vì chưa chứa đầy đủ "
            "hợp đồng tạo gói. Reader vẫn hỗ trợ; hãy chọn v5.2.2 để tạo hoặc sửa gói."
        )
    try:
        registry = load_reference_registry_tolerant()
    except (OSError, ValueError) as exc:
        st.error(f"Không nạp được registry dữ liệu tham chiếu: {exc}")
        return
    for warning in registry.warnings:
        st.warning(warning)

    datasets = registry.datasets
    dataset_by_id = {dataset.set_id: dataset for dataset in datasets}
    options: list[str | None] = [None, *dataset_by_id]
    selection_key = "reference_dataset_id"
    if st.session_state.get(selection_key) not in options:
        st.session_state[selection_key] = registry.default_set

    prompt_version = document.version_label.removeprefix("v")

    def dataset_label(value: str | None) -> str:
        if value is None:
            return "Không sử dụng bộ mẫu"
        dataset = dataset_by_id[value]
        compatibility = "tương thích" if dataset.prompt_version == prompt_version else f"prompt {dataset.prompt_version}"
        stages = ", ".join(dataset.packages) or "project"
        return f"{dataset.label} — {compatibility} — {stages}"

    default_index = options.index(registry.default_set) if registry.default_set in options else 0
    dataset_control, refresh_control = st.columns([5, 1])
    with dataset_control:
        selected_id = st.selectbox(
            "Bộ mẫu tham chiếu",
            options,
            index=default_index,
            format_func=dataset_label,
            key=selection_key,
            help="Lựa chọn được ghi nhớ trong phiên làm việc hiện tại.",
        )
    with refresh_control:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if st.button(
            "↻ Làm mới",
            key="refresh_reference_datasets",
            help="Nạp lại registry và trạng thái các bộ mẫu.",
            width="stretch",
        ):
            st.rerun()
    selected_dataset = dataset_by_id.get(selected_id) if selected_id is not None else None
    if selected_dataset is None:
        st.info("○ Chưa chọn bộ mẫu. Bạn vẫn có thể đọc và tra cứu hợp đồng prompt.")
    else:
        details = [f"Prompt {selected_dataset.prompt_version}"]
        if selected_dataset.tags:
            details.append(" · ".join(selected_dataset.tags))
        st.caption(" · ".join(details))
        if selected_dataset.prompt_version != prompt_version:
            st.warning(
                f"Bộ này dành cho prompt {selected_dataset.prompt_version}, không khớp {document.version_label}. "
                "Bạn vẫn có thể kiểm tra bộ mẫu ở chế độ chỉ đọc."
            )
    reader, structure, references = st.tabs(
        ["Tra cứu", "Tổng quan hợp đồng", "Dữ liệu tham chiếu"]
    )
    with reader:
        _render_document(document)
    with structure:
        _render_structure(document)
    with references:
        if selected_dataset is None:
            render_empty_state(
                "Chưa chọn bộ mẫu",
                "Chọn một bộ mẫu ở phía trên để kiểm tra package và gói truyện tham chiếu.",
                icon="○",
            )
        else:
            st.markdown("#### Package theo giai đoạn")
            _render_reference_packages(selected_dataset)
            st.markdown("#### Gói truyện tham chiếu")
            _render_reference_story(dataset=selected_dataset)


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
