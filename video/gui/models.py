from __future__ import annotations

import json

import streamlit as st

from studio.ui_components import confirm_destructive_action
from video.model_store import (
    format_size,
    models_root,
    prune_empty_model_directories,
    remove_model_store_path,
    scan_model_store,
)


def render_models_tab(_settings: dict[str, object]) -> None:
    st.subheader("Mô hình")
    root = models_root(__file__)
    st.caption(f"Kho model: {root}")
    controls = st.columns([1.2, 1.0, 1.0])
    include_cache = controls[0].checkbox("Bao gồm cache", value=False, key="video_models_include_cache")
    max_depth = controls[1].number_input("Độ sâu", min_value=1, max_value=8, value=3, step=1, key="video_models_depth")
    if controls[2].button("Làm mới", key="video_models_refresh", width="stretch"):
        st.rerun()
    report = scan_model_store(__file__, include_cache=include_cache, max_depth=int(max_depth))
    metrics = st.columns(3)
    metrics[0].metric("Dung lượng", format_size(report.size_bytes))
    metrics[1].metric("Tệp", report.file_count)
    metrics[2].metric("Thư mục", report.directory_count)
    rows = [{"Đường dẫn": e.relative_path, "Loại": e.kind, "Dung lượng": format_size(e.size_bytes), "Tệp": e.file_count, "Thư mục": e.directory_count} for e in report.entries]
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True, height=360)
    else:
        st.info("Chưa có model cục bộ trong kho này.")
    st.download_button("Tải báo cáo JSON", data=json.dumps(report.as_dict(), ensure_ascii=False, indent=2), file_name="video_models_report.json", mime="application/json", key="video_models_download", width="stretch")
    st.divider()
    left, right = st.columns(2)
    with left:
        prune_confirm = confirm_destructive_action(
            "Tôi xác nhận xóa các thư mục rỗng",
            key="video_models_prune_confirm",
        )
        if st.button("Prune thư mục rỗng", key="video_models_prune", disabled=not prune_confirm, width="stretch"):
            paths = prune_empty_model_directories(__file__, apply=True)
            st.success(f"Đã xoá {len(paths)} thư mục rỗng.")
            if paths:
                st.code("\n".join(paths))
    with right:
        remove_path = st.text_input("Đường dẫn cần xoá (tương đối)", key="video_models_remove_path")
        remove_confirm = confirm_destructive_action(
            "Tôi xác nhận xóa mô hình đã chọn",
            key="video_models_remove_confirm",
        )
        if st.button("Xoá model", key="video_models_remove", disabled=not remove_path.strip() or not remove_confirm, width="stretch"):
            try:
                target = remove_model_store_path(remove_path, __file__, apply=True)
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))
            else:
                st.success(f"Đã xoá: {target}")
                st.rerun()
