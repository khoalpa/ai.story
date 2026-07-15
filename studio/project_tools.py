"""Repository-wide tools owned by the Studio integration package."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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
