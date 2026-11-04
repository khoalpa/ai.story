"""Repository-wide tools owned by the Studio integration package."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from studio.artifact_validation import validate_project
from studio.json_formatter import (
    choose_json_file,
    default_formatted_path,
    format_json_file,
    save_formatted_json,
)
from studio.prompt_contract import load_prompt_contract


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_project_root() / "scripts" / script)],
        cwd=_project_root(), text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=False,
    )


def render_project_tools_workspace(*, embedded: bool = False) -> None:
    import streamlit as st

    if not embedded:
        st.set_page_config(page_title="Project Tools", page_icon=":material/build:", layout="wide")
    st.header("Công cụ dự án")
    st.caption("Các lệnh QA toàn repository; công cụ riêng của từng gói vẫn nằm trong ứng dụng tương ứng.")
    contract = load_prompt_contract()
    st.caption(
        f"Prompt chuẩn tự động: v{contract.version_label} · SHA-256 {contract.sha256[:12]}… · "
        f"`{contract.path}`"
    )

    with st.expander("Làm đẹp tệp JSON", expanded=False):
        st.caption(
            "Định dạng JSON UTF-8 để dễ đọc; giữ nguyên thứ tự khóa và tiếng Việt. "
            "Whitespace thay đổi sẽ làm SHA-256 của tệp thay đổi."
        )
        default_json_path = str((Path.cwd() / "output" / "visual_plan.json").resolve())
        st.session_state.setdefault("studio_json_formatter_path", default_json_path)
        path_columns = st.columns([5, 1], vertical_alignment="bottom")
        if path_columns[1].button(
            "Chọn tệp",
            key="studio_json_formatter_choose_file",
            use_container_width=True,
        ):
            try:
                selected_json_path = choose_json_file(
                    str(st.session_state.get("studio_json_formatter_path") or default_json_path)
                )
                if selected_json_path:
                    st.session_state["studio_json_formatter_path"] = selected_json_path
                st.session_state.pop("studio_json_formatter_picker_error", None)
            except Exception as exc:
                st.session_state["studio_json_formatter_picker_error"] = str(exc)
        json_path_text = path_columns[0].text_input(
            "Tệp JSON",
            key="studio_json_formatter_path",
        )
        picker_error = st.session_state.get("studio_json_formatter_picker_error")
        if picker_error:
            st.error(f"Không thể mở hộp thoại chọn tệp: {picker_error}")
        option_columns = st.columns(2)
        indent = option_columns[0].selectbox(
            "Thụt lề", [2, 4], key="studio_json_formatter_indent"
        )
        newline = option_columns[1].selectbox(
            "Xuống dòng", ["LF", "CRLF"], key="studio_json_formatter_newline"
        )
        formatter_signature = (json_path_text, int(indent), str(newline))
        if st.button("Phân tích và xem trước", key="studio_json_formatter_preview"):
            try:
                st.session_state["studio_json_formatter_result"] = format_json_file(
                    Path(json_path_text), indent=int(indent), newline=str(newline)
                )
                st.session_state["studio_json_formatter_signature"] = formatter_signature
                st.session_state.pop("studio_json_formatter_error", None)
            except (OSError, UnicodeError, ValueError) as exc:
                st.session_state.pop("studio_json_formatter_result", None)
                st.session_state.pop("studio_json_formatter_signature", None)
                st.session_state["studio_json_formatter_error"] = str(exc)

        formatter_error = st.session_state.get("studio_json_formatter_error")
        if formatter_error:
            st.error(f"Không thể làm đẹp JSON: {formatter_error}")
        result = st.session_state.get("studio_json_formatter_result")
        if (
            result is not None
            and st.session_state.get("studio_json_formatter_signature") != formatter_signature
        ):
            st.info("Đường dẫn hoặc tùy chọn đã đổi; hãy phân tích lại trước khi lưu.")
            result = None
        if result is not None:
            st.success(
                f"JSON hợp lệ · {result.original_lines:,} → {result.formatted_lines:,} dòng · "
                f"{result.original_bytes:,} → {result.formatted_bytes:,} byte"
            )
            preview_lines = result.text.splitlines()
            preview = "\n".join(preview_lines[:200])
            if len(preview_lines) > 200:
                preview += f"\n… ({len(preview_lines) - 200:,} dòng khác)"
            st.code(preview, language="json", line_numbers=True)

            overwrite = st.checkbox(
                "Ghi đè tệp nguồn (tự tạo .bak)",
                value=False,
                key="studio_json_formatter_overwrite",
            )
            suggested = result.source if overwrite else default_formatted_path(result.source)
            destination_text = st.text_input(
                "Tệp đích",
                value=str(suggested),
                key=(
                    "studio_json_formatter_destination_overwrite"
                    if overwrite
                    else "studio_json_formatter_destination_copy"
                ),
            )
            confirmed = True
            if overwrite:
                st.warning(
                    "Ghi đè sẽ thay đổi byte và SHA-256 của artifact. "
                    "Các manifest hoặc báo cáo liên quan có thể cần tạo lại."
                )
                confirmed = st.checkbox(
                    "Tôi xác nhận ghi đè tệp nguồn",
                    value=False,
                    key="studio_json_formatter_confirm_overwrite",
                )
            if st.button(
                "Lưu JSON đã làm đẹp",
                disabled=not confirmed,
                key="studio_json_formatter_save",
            ):
                try:
                    target, backup = save_formatted_json(
                        result,
                        Path(destination_text),
                        overwrite_source=overwrite,
                        create_backup=True,
                    )
                    message = f"Đã lưu và xác minh: {target}"
                    if backup is not None:
                        message += f" · Bản sao lưu: {backup}"
                    st.success(message)
                    st.info("Hãy chạy lại Prompt conformance audit nếu tệp thuộc package chuẩn.")
                except (OSError, UnicodeError, ValueError) as exc:
                    st.error(f"Không thể lưu JSON: {exc}")

    audit_path = st.text_input(
        "Artifact cần audit",
        value=str((Path.cwd() / "output").resolve()),
        key="studio_prompt_audit_path",
        help="Thư mục output hoặc một ZIP đúng gói v4.1.6. Gói cũ không được hỗ trợ.",
    )
    if st.button("Prompt conformance audit", key="studio_tool_prompt_audit"):
        results = validate_project(Path(audit_path).expanduser(), contract)
        st.dataframe(
            [{
                "Artifact": item.artifact, "Trạng thái": item.status,
                "Lỗi": len(item.errors), "Cảnh báo": len(item.warnings),
                "Prompt": item.prompt_version,
            } for item in results],
            hide_index=True, width="stretch",
        )
        for item in results:
            with st.expander(f"{item.artifact} · {item.status}"):
                st.json(item.as_dict(), expanded=False)
    for label, script in {
        "Dependency check": "check_dependency_direction.py",
        "Wheel contents": "check_wheel_contents.py",
        "Release smoke": "release_smoke.py",
    }.items():
        if st.button(label, key=f"studio_tool_{script}"):
            result = _run(script)
            (st.success if result.returncode == 0 else st.error)(f"{label}: exit {result.returncode}")
            if result.stdout:
                st.code(result.stdout)
            if result.stderr:
                st.code(result.stderr)


__all__ = ["render_project_tools_workspace"]
