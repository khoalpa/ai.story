"""Repository-wide tools owned by the Studio integration package."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from studio.artifact_validation import validate_project
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
    st.header("Project Tools")
    st.caption("Repository-wide QA commands; package tools remain in each standalone app.")
    contract = load_prompt_contract()
    st.caption(
        f"Prompt chuẩn tự động: v{contract.version_label} · SHA-256 {contract.sha256[:12]}… · "
        f"`{contract.path}`"
    )
    audit_path = st.text_input(
        "Artifact cần audit",
        value=str((Path.cwd() / "output").resolve()),
        key="studio_prompt_audit_path",
        help="Thư mục output, stage2_checkpoint.zip hoặc story.zip.",
    )
    if st.button("Prompt conformance audit", key="studio_tool_prompt_audit"):
        results = validate_project(Path(audit_path).expanduser(), contract)
        st.dataframe(
            [{
                "Artifact": item.artifact, "Trạng thái": item.status,
                "Lỗi": len(item.errors), "Cảnh báo": len(item.warnings),
                "Prompt": item.prompt_version,
            } for item in results],
            hide_index=True, use_container_width=True,
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
