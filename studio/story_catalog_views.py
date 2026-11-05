"""Streamlit workspace for producing story_catalog.json."""
from __future__ import annotations

from pathlib import Path

from studio.project_context import CATALOG_DIRECTORY_KEY, choose_catalog_directory
from studio.story_catalog import (
    CATALOG_FILENAME,
    DEFAULT_CATALOG_ROOT,
    catalog_bytes,
    scan_story_catalog,
    write_story_catalog,
)


def render_story_catalog_workspace() -> None:
    import streamlit as st

    state = st.session_state
    state.setdefault(CATALOG_DIRECTORY_KEY, str(DEFAULT_CATALOG_ROOT.resolve()))
    left, right = st.columns([5, 1])
    left.text_input("Thư mục chứa các gói truyện", key=CATALOG_DIRECTORY_KEY)
    if right.button("Chọn thư mục…", use_container_width=True):
        choose_catalog_directory(state)
        st.rerun()
    if state.get("story_catalog_directory_error"):
        st.error(state["story_catalog_directory_error"])
    recursive = st.checkbox(
        "Quét đệ quy",
        value=False,
        help="Mặc định chỉ quét gói ở cấp đầu và các ZIP ngay trong từng thư mục con.",
    )
    include_paths = st.checkbox(
        "Bao gồm đường dẫn tuyệt đối",
        value=False,
        help="Tắt mặc định để catalog có thể đính kèm an toàn và dùng trên máy khác.",
    )
    if st.button("Quét và tạo danh sách", type="primary"):
        try:
            state["story_catalog_result"] = scan_story_catalog(
                Path(str(state[CATALOG_DIRECTORY_KEY])), recursive=recursive,
                include_absolute_paths=include_paths,
            )
            state.pop("story_catalog_error", None)
        except (OSError, ValueError) as exc:
            state["story_catalog_error"] = str(exc)
    if state.get("story_catalog_error"):
        st.error(state["story_catalog_error"])
    catalog = state.get("story_catalog_result")
    if not isinstance(catalog, dict):
        st.info("Chọn thư mục rồi quét để tạo danh sách các gói truyện hiện có.")
        return
    summary = catalog["summary"]
    columns = st.columns(4)
    for column, label, key in zip(columns, ("Truyện", "Biến thể gói", "Nguồn lỗi", "Nhóm trùng"),
                                  ("story_count", "package_variant_count", "invalid_source_count", "duplicate_group_count")):
        column.metric(label, summary[key])
    st.dataframe([
        {"Tiêu đề": row["title"], "Series": row["series"], "Tập": row["episode"],
         "Thể loại": row["genre"], "Số gói": len(row["package_variants"])}
        for row in catalog["stories"]
    ], use_container_width=True, hide_index=True)
    if catalog["duplicate_groups"]:
        with st.expander("Các nhóm có khả năng trùng"):
            st.json(catalog["duplicate_groups"], expanded=False)
    if catalog["invalid_sources"]:
        with st.expander("Nguồn không hợp lệ"):
            st.json(catalog["invalid_sources"], expanded=False)
    raw = catalog_bytes(catalog)
    download, save = st.columns(2)
    download.download_button("Tải story_catalog.json", raw, file_name=CATALOG_FILENAME,
                             mime="application/json", use_container_width=True)
    if save.button("Lưu vào thư mục đang chọn", use_container_width=True):
        try:
            destination = write_story_catalog(catalog, Path(str(state[CATALOG_DIRECTORY_KEY])) / CATALOG_FILENAME)
            st.success(f"Đã lưu: {destination}")
        except OSError as exc:
            st.error(f"Không thể lưu catalog: {exc}")


__all__ = ["render_story_catalog_workspace"]
