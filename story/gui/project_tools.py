from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

from story.model_store import (
    format_size,
    models_root,
    prune_empty_model_directories,
    remove_model_store_path,
    scan_model_store,
)
from story.project_cleanup import apply_cleanup_plan, build_cleanup_plan
from story.runtime import resolve_project_root


def _project_root() -> Path:
    return resolve_project_root(__file__)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _render_cleanup_tool() -> None:
    st.subheader("Project cleanup")
    root = _project_root()
    cols = st.columns(3)
    include_runtime = cols[0].checkbox("Runtime outputs", key="project_cleanup_include_runtime")
    include_venv = cols[1].checkbox("Virtual envs", key="project_cleanup_include_venv")
    include_models = cols[2].checkbox("Models", key="project_cleanup_include_models")

    plan = build_cleanup_plan(
        root,
        include_runtime=include_runtime,
        include_venv=include_venv,
        include_models=include_models,
    )
    st.metric("Matched artifacts", plan.count)

    rows = [
        {"type": "dir", "path": _relative(path, root)}
        for path in plan.directories
    ] + [
        {"type": "file", "path": _relative(path, root)}
        for path in plan.files
    ]
    if rows:
        st.dataframe(rows, width="stretch", height=240)
    else:
        st.caption("No matching artifacts.")

    confirm = st.checkbox("Confirm cleanup", key="project_cleanup_confirm")
    if st.button("Clean now", key="project_cleanup_apply", disabled=not confirm or plan.count == 0, width="stretch"):
        apply_cleanup_plan(plan)
        st.success(f"Removed {plan.count} artifact(s).")
        rerun_fn = getattr(st, "rerun", None)
        if callable(rerun_fn):
            rerun_fn()


def _render_model_manager() -> None:
    st.subheader("Models")
    root = models_root(__file__)
    st.caption(str(root))

    controls = st.columns([1.0, 1.0, 1.0])
    include_cache = controls[0].checkbox("Include cache", value=True, key="models_gui_include_cache")
    max_depth = controls[1].number_input("Depth", min_value=1, max_value=6, value=2, step=1, key="models_gui_depth")
    if controls[2].button("Refresh", key="models_gui_refresh", width="stretch"):
        st.session_state["models_gui_refreshed"] = True

    report = scan_model_store(__file__, include_cache=include_cache, max_depth=int(max_depth))
    metric_cols = st.columns(3)
    metric_cols[0].metric("Size", format_size(report.size_bytes))
    metric_cols[1].metric("Files", report.file_count)
    metric_cols[2].metric("Dirs", report.directory_count)
    report_json = json.dumps(report.as_dict(), ensure_ascii=False, indent=2)
    st.download_button(
        "Download JSON report",
        data=report_json,
        file_name="models_report.json",
        mime="application/json",
        key="models_gui_download_json",
        width="stretch",
    )

    rows = []
    for entry in report.entries:
        rows.append({
            "path": entry.relative_path,
            "kind": entry.kind,
            "size": format_size(entry.size_bytes),
            "files": entry.file_count,
            "dirs": entry.directory_count,
        })
    if rows:
        st.dataframe(rows, width="stretch", height=320)
    else:
        st.caption("No local model entries.")

    st.divider()
    action_cols = st.columns([1.0, 2.0])
    with action_cols[0]:
        apply_prune = st.checkbox("Apply prune", key="models_gui_apply_prune")
        if st.button("Prune empty dirs", key="models_gui_prune_empty", width="stretch"):
            paths = prune_empty_model_directories(__file__, apply=apply_prune)
            if apply_prune:
                st.success(f"Removed {len(paths)} empty directorie(s).")
            else:
                st.info(f"Would remove {len(paths)} empty directorie(s).")
            if paths:
                st.code("\n".join(paths))

    with action_cols[1]:
        remove_path = st.text_input("Remove path", key="models_gui_remove_path")
        apply_remove = st.checkbox("Apply remove", key="models_gui_apply_remove")
        if st.button("Remove selected path", key="models_gui_remove", disabled=not remove_path.strip(), width="stretch"):
            try:
                target = remove_model_store_path(remove_path, __file__, apply=apply_remove)
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))
            else:
                if apply_remove:
                    st.success(f"Removed: {target}")
                else:
                    st.info(f"Would remove: {target}")


def _run_project_command(command: list[str], *, timeout: int = 600) -> dict[str, object]:
    root = _project_root()
    try:
        proc = subprocess.run(
            command,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": " ".join(command),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "ok": False,
            "error": f"Timed out after {timeout}s",
        }


def _script_command(script_name: str) -> list[str]:
    return [sys.executable, str(_project_root() / "scripts" / script_name)]


def _store_qa_result(key: str, result: dict[str, object]) -> None:
    st.session_state[key] = result


def _render_command_result(key: str) -> None:
    result = st.session_state.get(key)
    if not isinstance(result, dict):
        return
    ok = bool(result.get("ok"))
    if ok:
        st.success(f"Command passed: {result.get('command')}")
    else:
        st.error(f"Command failed: {result.get('command')}")
    if result.get("stdout"):
        st.code(str(result.get("stdout") or ""), language="text")
    if result.get("stderr"):
        st.code(str(result.get("stderr") or ""), language="text")
    if result.get("error"):
        st.warning(str(result.get("error") or ""))


def _render_qa_release() -> None:
    st.subheader("QA / Release")
    st.caption(str(_project_root()))

    qa_cols = st.columns(3)
    if qa_cols[0].button("Dependency check", key="qa_dependency_check", width="stretch"):
        _store_qa_result(
            "qa_dependency_check_result",
            _run_project_command(_script_command("check_dependency_direction.py"), timeout=180),
        )
    if qa_cols[1].button("Wheel contents", key="qa_wheel_contents", width="stretch"):
        _store_qa_result(
            "qa_wheel_contents_result",
            _run_project_command(_script_command("check_wheel_contents.py"), timeout=600),
        )
    if qa_cols[2].button("Release smoke", key="qa_release_smoke", width="stretch"):
        _store_qa_result(
            "qa_release_smoke_result",
            _run_project_command(_script_command("release_smoke.py"), timeout=900),
        )

    for key in ("qa_dependency_check_result", "qa_wheel_contents_result", "qa_release_smoke_result"):
        _render_command_result(key)

    st.divider()
    st.markdown("#### Build artifacts")
    confirm_build = st.checkbox("Confirm build dist", key="qa_confirm_build_dist")
    if st.button("Build dist", key="qa_build_dist", disabled=not confirm_build, width="stretch"):
        _store_qa_result(
            "qa_build_dist_result",
            _run_project_command(_script_command("build_dist.py"), timeout=600),
        )
    _render_command_result("qa_build_dist_result")

    st.divider()
    st.markdown("#### Release helpers")
    release_cols = st.columns(2)
    with release_cols[0]:
        confirm_sync = st.checkbox("Confirm sync version", key="qa_confirm_sync_version")
        if st.button("Sync version", key="qa_sync_version", disabled=not confirm_sync, width="stretch"):
            _store_qa_result(
                "qa_sync_version_result",
                _run_project_command(_script_command("sync_version.py"), timeout=180),
            )
        _render_command_result("qa_sync_version_result")

    with release_cols[1]:
        confirm_zip = st.checkbox("Confirm clean release zip", key="qa_confirm_clean_release_zip")
        if st.button("Make clean release zip", key="qa_clean_release_zip", disabled=not confirm_zip, width="stretch"):
            _store_qa_result(
                "qa_clean_release_zip_result",
                _run_project_command(_script_command("make_clean_release.py"), timeout=600),
            )
        _render_command_result("qa_clean_release_zip_result")


def render_project_tools_workspace(*, embedded: bool = False) -> None:
    if not embedded:
        st.set_page_config(page_title="Project Tools", page_icon=":material/build:", layout="wide")
    st.header("Project Tools")
    cleanup_tab, models_tab, qa_tab = st.tabs(["Cleanup", "Models", "QA / Release"])
    with cleanup_tab:
        _render_cleanup_tool()
    with models_tab:
        _render_model_manager()
    with qa_tab:
        _render_qa_release()
