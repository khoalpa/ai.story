from __future__ import annotations

from pathlib import Path
import json
from typing import Callable

import streamlit as st

from .workspace_state import (
    clear_global_run_timeline,
    ensure_global_run_monitor_state,
    ensure_workspace_shell_state,
    get_global_run_monitor_snapshot,
    get_global_run_timeline,
    get_pipeline_status_snapshot,
    request_workspace_navigation,
    sync_pipeline_handoff_state,
)
from .runtime_usage import render_runtime_usage_compact, set_runtime_usage_container
from .progress_details import summarize_progress_details
from .workspace_navigation import workspace_navigation_state
from .workspace_handoff import workspace_handoff_state
from .workspace_source_outputs import workspace_source_outputs

OverviewRenderer = Callable[[], None]
WORKSPACE_SIDEBAR_EXPANDED_KEY = "workspace_sidebar_expanded"


def _workspace_sidebar_initial_state() -> str:
    st.session_state.setdefault(WORKSPACE_SIDEBAR_EXPANDED_KEY, True)
    return "expanded" if st.session_state[WORKSPACE_SIDEBAR_EXPANDED_KEY] else "collapsed"


def _collapse_workspace_sidebar() -> None:
    st.session_state[WORKSPACE_SIDEBAR_EXPANDED_KEY] = False
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        rerun_fn()


def _expand_workspace_sidebar() -> None:
    st.session_state[WORKSPACE_SIDEBAR_EXPANDED_KEY] = True
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        rerun_fn()


def _path_exists(value: str) -> bool:
    return bool(value) and Path(value).exists()


def _path_file_exists(value: str) -> bool:
    return bool(value) and Path(value).is_file()


def _path_dir_exists(value: str) -> bool:
    return bool(value) and Path(value).is_dir()


def _story_ready_detail() -> tuple[str, list[str]]:
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    missing: list[str] = []
    if not (handoff.story_plain_script_text or _path_file_exists(outputs.story_plain_script_path) or _path_exists(handoff.last_story_output)):
        missing.append("plain script or Story output")
    if not _path_dir_exists(handoff.story_image_handoff_dir):
        missing.append("image handoff dir")
    if not _path_dir_exists(handoff.story_video_handoff_dir):
        missing.append("video story bundle")
    return ("ready" if not missing else ("partial" if len(missing) < 3 else "missing"), missing)


def _audio_ready_detail() -> tuple[str, list[str]]:
    handoff = workspace_handoff_state(st.session_state)
    missing: list[str] = []
    if not _path_exists(handoff.audio_output_path):
        missing.append("audio output")
    if not _path_file_exists(handoff.audio_srt_path):
        missing.append("subtitle .srt")
    return ("ready" if not missing else ("partial" if len(missing) == 1 else "missing"), missing)


def _image_ready_detail() -> tuple[str, list[str]]:
    handoff = workspace_handoff_state(st.session_state)
    missing: list[str] = []
    if not _path_file_exists(handoff.image_cover_path):
        missing.append("cover image")
    if not _path_dir_exists(handoff.image_scenes_dir):
        missing.append("scene images dir")
    if not _path_file_exists(handoff.image_manifest_path):
        missing.append("image manifest")
    return ("ready" if not missing else ("partial" if len(missing) < 3 else "missing"), missing)


def _video_ready_detail() -> tuple[str, list[str]]:
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    missing: list[str] = []
    if not _path_exists(handoff.audio_output_path):
        missing.append("audio input")
    if not (_path_file_exists(handoff.image_cover_path) or _path_dir_exists(handoff.story_video_handoff_dir)):
        missing.append("cover image or Story bundle")
    if not (_path_dir_exists(handoff.image_scenes_dir) or _path_dir_exists(handoff.story_video_handoff_dir)):
        missing.append("scene images or Story bundle")
    if not _path_exists(outputs.video_output):
        missing.append("latest video output")
    return ("ready" if len(missing) <= 1 else ("partial" if len(missing) <= 3 else "missing"), missing)


def _readiness_badge(status: str) -> str:
    normalized = str(status or "missing").lower()
    if normalized == "ready":
        return "[ready] ready"
    if normalized == "partial":
        return "[partial] partial"
    return "[missing] missing"


def _story_plain_display_value() -> str:
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    if _path_file_exists(outputs.story_plain_script_path):
        return str(outputs.story_plain_script_path)
    if _path_file_exists(handoff.last_story_output):
        return str(handoff.last_story_output)
    if handoff.story_plain_script_text or handoff.last_story_output or outputs.story_plain_script_path:
        return "Plain script ready for Audio."
    return ""


def _story_plain_available() -> bool:
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    return bool(handoff.story_plain_script_text or _path_file_exists(outputs.story_plain_script_path) or _path_exists(handoff.last_story_output))


def _load_text_from_path(value: str) -> str:
    path = Path(str(value or ""))
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _guess_video_output_from_audio(audio_path: str) -> str:
    audio_file = Path(str(audio_path or "").strip())
    if not str(audio_file):
        return str(Path("output") / "story.mp4")
    current = Path(str(st.session_state.get("video_output_input") or "").strip() or "output/story.mp4")
    out_dir = current.parent if str(current.parent) else Path("output")
    return str(out_dir / f"{audio_file.stem}.mp4")


def _load_story_bundle_manifest(bundle_dir: Path) -> dict[str, object]:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found in bundle: {bundle_dir}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _apply_story_to_audio() -> bool:
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    plain_text = str(handoff.story_plain_script_text or "")
    if not plain_text:
        plain_text = _load_text_from_path(outputs.story_plain_script_path)
    if not plain_text:
        plain_text = _load_text_from_path(handoff.last_story_output)
    if not plain_text:
        return False
    st.session_state["run_plain_text"] = plain_text
    st.session_state["last_plain_script"] = plain_text
    st.session_state["audio_last_auto_plain_script"] = plain_text
    st.session_state["audio_lock_to_story_handoff"] = True
    return True


def _apply_story_to_image() -> bool:
    handoff = workspace_handoff_state(st.session_state)
    if not _path_dir_exists(handoff.story_image_handoff_dir):
        return False
    st.session_state["image_source_kind"] = "handoff"
    st.session_state["image_handoff_dir"] = handoff.story_image_handoff_dir
    st.session_state["image_lock_to_story_handoff"] = True
    if not str(st.session_state.get("image_output_dir") or "").strip():
        st.session_state["image_output_dir"] = str(Path(handoff.story_image_handoff_dir) / "generated")
    return True


def _apply_story_bundle_to_video() -> bool:
    handoff = workspace_handoff_state(st.session_state)
    bundle_dir = Path(str(handoff.story_video_handoff_dir or "").strip())
    if not bundle_dir.is_dir():
        return False
    manifest = _load_story_bundle_manifest(bundle_dir)
    scene_dir = bundle_dir / str(manifest.get("scene_images_dir") or "scene_images")
    cover_path = bundle_dir / str((manifest.get("cover_prompt") or {}).get("expected_image_file") or "cover.png")
    st.session_state["video_cover_source"] = "handoff"
    st.session_state["video_scenes_source"] = "handoff"
    st.session_state["video_cover_input"] = str(cover_path)
    st.session_state["video_scenes_input"] = str(scene_dir)
    if not str(st.session_state.get("video_output_input") or "").strip():
        st.session_state["video_output_input"] = str(Path("output") / "story.mp4")
    handoff.story_video_handoff_dir = str(bundle_dir)
    handoff.image_manifest_path = str(bundle_dir / "manifest.json")
    if cover_path.exists():
        handoff.image_cover_path = str(cover_path)
    if scene_dir.exists():
        handoff.image_scenes_dir = str(scene_dir)
    return True


def _apply_audio_to_video() -> bool:
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    audio_path = str(handoff.audio_output_path or outputs.audio_output or "")
    if not _path_exists(audio_path):
        return False
    st.session_state["video_audio_input"] = audio_path
    st.session_state["video_lock_to_audio_handoff"] = True
    st.session_state["workspace_video_last_auto_audio_input"] = audio_path
    if _path_file_exists(handoff.audio_srt_path or outputs.audio_srt_output):
        srt_path = str(handoff.audio_srt_path or outputs.audio_srt_output)
        st.session_state["video_subtitle_input"] = srt_path
        st.session_state["workspace_video_last_auto_subtitle_input"] = srt_path
    st.session_state["video_output_input"] = _guess_video_output_from_audio(audio_path)
    st.session_state["workspace_video_last_auto_output_input"] = st.session_state["video_output_input"]
    return True


def _apply_image_to_video() -> bool:
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    cover = str(handoff.image_cover_path or outputs.image_cover_output or "")
    scenes = str(handoff.image_scenes_dir or outputs.image_scenes_dir or "")
    manifest = str(handoff.image_manifest_path or "")
    if not (_path_file_exists(cover) or _path_dir_exists(scenes) or _path_file_exists(manifest)):
        return False
    st.session_state["video_cover_source"] = "handoff"
    st.session_state["video_scenes_source"] = "handoff"
    st.session_state["video_lock_to_image_handoff"] = True
    if cover:
        st.session_state["video_cover_input"] = cover
        st.session_state["workspace_video_last_auto_cover_input"] = cover
    if scenes:
        st.session_state["video_scenes_input"] = scenes
        st.session_state["workspace_video_last_auto_scenes_input"] = scenes
    return True


def _action_label_for_row(row: dict[str, str]) -> str:
    mapping = {
        "Story -> Audio - plain script": "Adopt latest Story plain",
        "Story -> Image - prompt bundle": "Apply latest Story handoff",
        "Story -> Video - bundle": "Use latest Story bundle",
        "Audio -> Video - audio": "Adopt latest Audio output",
        "Audio -> Video - subtitle": "Adopt latest Audio output",
        "Image -> Video - cover": "Apply latest Image handoff",
        "Image -> Video - scenes": "Apply latest Image handoff",
        "Image -> Video - manifest": "Apply latest Image handoff",
    }
    return mapping.get(row.get("handoff", ""), "Apply latest")


def _perform_row_action(row: dict[str, str]) -> tuple[bool, str]:
    handoff_name = row.get("handoff", "")
    try:
        if handoff_name == "Story -> Audio - plain script":
            ok = _apply_story_to_audio()
        elif handoff_name == "Story -> Image - prompt bundle":
            ok = _apply_story_to_image()
        elif handoff_name == "Story -> Video - bundle":
            ok = _apply_story_bundle_to_video()
        elif handoff_name in {"Audio -> Video - audio", "Audio -> Video - subtitle"}:
            ok = _apply_audio_to_video()
        elif handoff_name in {"Image -> Video - cover", "Image -> Video - scenes", "Image -> Video - manifest"}:
            ok = _apply_image_to_video()
        else:
            return False, "No automatic action is available for this row yet."
    except Exception as exc:
        return False, str(exc)
    if not ok:
        return False, "The current handoff/output source is not ready for automatic apply."
    return True, _action_label_for_row(row) + " succeeded."


def _build_handoff_readiness_rows() -> list[dict[str, str]]:
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    rows: list[dict[str, str]] = []

    def add_row(*, handoff_name: str, current_value: str, ok: bool, missing_text: str, app_name: str, target_view: str, target_field: str, fix_label: str) -> None:
        rows.append({
            "handoff": handoff_name,
            "status": "ready" if ok else "missing",
            "detail": current_value if current_value else missing_text,
            "app_name": app_name,
            "target_view": target_view,
            "target_field": target_field,
            "fix_label": fix_label,
            "action_label": _action_label_for_row({"handoff": handoff_name}),
        })

    story_plain_value = _story_plain_display_value()
    add_row(handoff_name="Story -> Audio - plain script", current_value=story_plain_value, ok=_story_plain_available(), missing_text="Missing plain script or Story output file.", app_name="Audio", target_view="Run", target_field="plain_script", fix_label="Open Audio")
    add_row(handoff_name="Story -> Image - prompt bundle", current_value=handoff.story_image_handoff_dir, ok=_path_dir_exists(handoff.story_image_handoff_dir), missing_text="Missing image handoff directory from Story.", app_name="Image", target_view="Inputs", target_field="prompt_bundle", fix_label="Open Image")
    add_row(handoff_name="Story -> Video - bundle", current_value=handoff.story_video_handoff_dir, ok=_path_dir_exists(handoff.story_video_handoff_dir), missing_text="Missing Story bundle for Video.", app_name="Video", target_view="Inputs", target_field="story_bundle", fix_label="Open Video")
    add_row(handoff_name="Audio -> Video - audio", current_value=handoff.audio_output_path or outputs.audio_output, ok=_path_exists(handoff.audio_output_path or outputs.audio_output), missing_text="Missing audio output for Video input.", app_name="Video", target_view="Inputs", target_field="audio_input", fix_label="Open Video")
    add_row(handoff_name="Audio -> Video - subtitle", current_value=handoff.audio_srt_path or outputs.audio_srt_output, ok=_path_file_exists(handoff.audio_srt_path or outputs.audio_srt_output), missing_text="Missing subtitle (.srt) from Audio.", app_name="Video", target_view="Inputs", target_field="subtitle_input", fix_label="Open Video")
    add_row(handoff_name="Image -> Video - cover", current_value=handoff.image_cover_path or outputs.image_cover_output, ok=_path_file_exists(handoff.image_cover_path or outputs.image_cover_output), missing_text="Missing cover image from Image.", app_name="Video", target_view="Inputs", target_field="cover_input", fix_label="Open Video")
    add_row(handoff_name="Image -> Video - scenes", current_value=handoff.image_scenes_dir or outputs.image_scenes_dir, ok=_path_dir_exists(handoff.image_scenes_dir or outputs.image_scenes_dir), missing_text="Missing scene images directory from Image.", app_name="Video", target_view="Inputs", target_field="scenes_input", fix_label="Open Video")
    add_row(handoff_name="Image -> Video - manifest", current_value=handoff.image_manifest_path, ok=_path_file_exists(handoff.image_manifest_path), missing_text="Missing image manifest for handoff review/debug.", app_name="Video", target_view="Inputs", target_field="manifest_input", fix_label="Open Video")
    add_row(handoff_name="Video output", current_value=outputs.video_output, ok=_path_exists(outputs.video_output), missing_text="No recent video output available.", app_name="Video", target_view="Preview & Logs", target_field="video_output", fix_label="Open Video")
    return rows


def _render_handoff_readiness_table() -> None:
    st.markdown("#### Handoff readiness detail")
    rows = _build_handoff_readiness_rows()
    status_message = st.session_state.pop("workspace_readiness_action_status", None)
    if isinstance(status_message, tuple) and len(status_message) == 2:
        level, message = status_message
        getattr(st, str(level) if str(level) in {"success", "warning", "error", "info"} else "info")(message)
    headers = st.columns([1.8, 0.8, 2.4, 1.0, 1.2])
    headers[0].markdown("**handoff**")
    headers[1].markdown("**status**")
    headers[2].markdown("**detail**")
    headers[3].markdown("**open**")
    headers[4].markdown("**action**")
    for idx, row in enumerate(rows):
        cols = st.columns([1.8, 0.8, 2.4, 1.0, 1.2])
        cols[0].write(row["handoff"])
        cols[1].write(_readiness_badge(row["status"]))
        cols[2].caption(row["detail"])
        if cols[3].button(row["fix_label"], key=f"handoff_fix_{idx}", width="stretch"):
            _navigate_to(row["app_name"], row["target_view"], row.get("target_field") or "")
        if row["handoff"] != "Video output":
            if cols[4].button(row["action_label"], key=f"handoff_action_{idx}", width="stretch"):
                ok, message = _perform_row_action(row)
                st.session_state["workspace_readiness_action_status"] = (("success" if ok else "warning"), message)
                _navigate_to(row["app_name"], row["target_view"], row.get("target_field") or "")
        else:
            cols[4].caption("-")


def _render_pipeline_readiness_block() -> None:
    readiness = [
        ("Story", *_story_ready_detail()),
        ("Audio", *_audio_ready_detail()),
        ("Image", *_image_ready_detail()),
        ("Video", *_video_ready_detail()),
    ]
    ready_count = sum(1 for _, status, _ in readiness if status in {"ready", "set", "rendered"})
    missing_count = len(readiness) - ready_count

    st.caption(f"Pipeline readiness: {ready_count}/{len(readiness)} ready, {missing_count} need attention")
    cols = st.columns(len(readiness))
    rows = []
    for col, (app, status, missing) in zip(cols, readiness):
        detail = ", ".join(missing) if missing else "Ready to continue."
        col.markdown(f"**{app}**")
        col.write(_readiness_badge(status))
        col.caption(detail)
        rows.append({
            "app": app,
            "status": _readiness_badge(status),
            "missing_or_pending": detail,
        })

    with st.expander("Readiness details and handoff fixes", expanded=False):
        st.dataframe(rows, width="stretch", height=150)
        _render_handoff_readiness_table()


def _apply_pending_navigation_before_widgets(app_options: list[str]) -> None:
    navigation = workspace_navigation_state(st.session_state)
    pending_app = navigation.pending_app
    pending_view = navigation.pending_view
    pending_field = navigation.pending_field

    if pending_app:
        if pending_app not in app_options:
            pending_app = "Overview"

        navigation.active_app = pending_app
        navigation.active_app_selector = pending_app

        if pending_view:
            if pending_app == "Story":
                navigation.set_target_view("Story", pending_view)
                st.session_state["story_embedded_view_selector"] = pending_view
            elif pending_app == "Audio":
                navigation.set_target_view("Audio", pending_view)
                st.session_state["audio_embedded_view_selector"] = pending_view
            elif pending_app == "Image":
                navigation.set_target_view("Image", pending_view)
                st.session_state["image_embedded_view_selector"] = pending_view
            elif pending_app == "Video":
                navigation.set_target_view("Video", pending_view)
                st.session_state["video_embedded_view_selector"] = pending_view

        if pending_field and pending_app in {"Story", "Audio", "Image", "Video"}:
            navigation.set_target_field(pending_app, pending_field)

        navigation.pending_app = ""
        navigation.pending_view = ""
        navigation.pending_field = ""


def _status_badge_text(label: str, value: str) -> str:
    normalized = (value or "").strip().lower()
    icon = "idle"
    if normalized == "ready":
        icon = "ready"
    elif normalized == "sent":
        icon = "sent"
    elif normalized == "rendered":
        icon = "rendered"
    return f"{label}: {icon} {value}"


def _navigate_to(app_name: str, target_view: str | None = None, target_field: str | None = None) -> None:
    request_workspace_navigation(app_name, target_view, target_field)
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        rerun_fn()


def _render_pipeline_status_bar() -> None:
    snapshot = get_pipeline_status_snapshot()
    st.markdown("### Pipeline status")
    cols = st.columns(4)

    story_target = "Preview & Logs" if snapshot.get("story") in {"ready", "sent"} else "Run"
    audio_target = "Run"
    image_target = "Preview & Logs" if snapshot.get("image") == "ready" else "Inputs"
    video_target = "Run" if snapshot.get("video") == "rendered" else "Inputs"

    items = [
        ("Story", snapshot.get("story", "idle"), story_target, "pipeline_nav_story"),
        ("Audio", snapshot.get("audio", "idle"), audio_target, "pipeline_nav_audio"),
        ("Image", snapshot.get("image", "idle"), image_target, "pipeline_nav_image"),
        ("Video", snapshot.get("video", "idle"), video_target, "pipeline_nav_video"),
    ]
    for col, (label, value, target, key) in zip(cols, items):
        with col:
            if st.button(
                _status_badge_text(label, value),
                key=key,
                width="stretch",
                help=f"Open the {label} studio and switch to the {target} tab.",
            ):
                _navigate_to(label, target)

    st.caption("Click a status item to open the matching studio and sub-tab.")


def _render_global_run_monitor() -> None:
    ensure_global_run_monitor_state()
    snap = get_global_run_monitor_snapshot()

    st.markdown("### Global run monitor")
    cols = st.columns([1.0, 1.0, 1.0, 2.2])

    app = str(snap.get("app") or "-")
    stage = str(snap.get("stage") or "-")
    status = str(snap.get("status") or "idle")
    progress_value = int(snap.get("progress") or 0)
    output = str(snap.get("output") or "")
    error = str(snap.get("error") or "")
    summary = snap.get("summary")

    cols[0].metric("App", app)
    cols[1].metric("Stage", stage)
    cols[2].metric("Status", status)

    with cols[3]:
        monitor_detail = summarize_progress_details(summary if isinstance(summary, dict) else None)
        monitor_text = f"{progress_value}% - {app} {stage} {status}"
        if monitor_detail:
            monitor_text = f"{monitor_text} | {monitor_detail}"
        st.progress(max(0.0, min(1.0, progress_value / 100.0)), text=monitor_text)

    detail_cols = st.columns([2.2, 1.0, 1.0])
    with detail_cols[0]:
        if output:
            if Path(output).exists():
                st.success(f"Output: {output}")
            else:
                st.info(f"Output: {output}")
        else:
            st.caption("No output path is available in the monitor.")

    with detail_cols[1]:
        if app in {"Story", "Audio", "Image", "Video"}:
            target_view = "Preview & Logs" if app in {"Story", "Image", "Video"} else "Run"
            if st.button("Open last job", key="open_last_job_from_monitor", width="stretch"):
                _navigate_to(app, target_view)

    with detail_cols[2]:
        if error:
            st.error("Latest error")
        else:
            st.caption("No recent error")

    if error:
        with st.expander("Last error", expanded=False):
            st.code(error)

    if summary:
        with st.expander("Last job summary", expanded=False):
            st.json(summary)


def _timeline_status_icon(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"completed", "rendered", "ready"}:
        return "done"
    if normalized in {"running", "sent"}:
        return "running"
    if normalized in {"failed", "error"}:
        return "failed"
    return "idle"


def _render_global_run_timeline() -> None:
    items = get_global_run_timeline()
    st.markdown("### Pipeline timeline")

    ctrl_cols = st.columns([1.2, 1.2, 1.0])
    with ctrl_cols[0]:
        app_filter = st.selectbox(
            "Filter app",
            options=["All", "Story", "Audio", "Image", "Video"],
            index=0,
            key="workspace_timeline_app_filter",
        )

    with ctrl_cols[1]:
        failed_only = st.checkbox(
            "Failed only",
            key="workspace_timeline_failed_only",
            help="Show only events whose status is failed/error.",
        )

    with ctrl_cols[2]:
        st.caption("")
        st.caption("")
        if st.button("Clear timeline", key="workspace_clear_timeline", width="stretch"):
            clear_global_run_timeline()
            rerun_fn = getattr(st, "rerun", None)
            if callable(rerun_fn):
                rerun_fn()

    if not items:
        st.caption("No job events are available in the timeline yet.")
        return

    filtered = list(items)
    if app_filter != "All":
        filtered = [x for x in filtered if str(x.get("app") or "") == app_filter]
    if failed_only:
        filtered = [
            x for x in filtered
            if str(x.get("status") or "").strip().lower() in {"failed", "error"}
        ]

    if not filtered:
        st.caption("No event matches the current filter.")
        return

    rows = []
    for item in filtered:
        rows.append(
            {
                "time": item.get("time", ""),
                "app": item.get("app", ""),
                "stage": item.get("stage", ""),
                "status": f"{_timeline_status_icon(str(item.get('status', '')))} {item.get('status', '')}",
                "message": item.get("message", ""),
                "output": item.get("output", ""),
            }
        )

    st.dataframe(rows, width="stretch", height=260)

    latest_error = next((x for x in filtered if x.get("error")), None)
    if latest_error:
        with st.expander("Latest timeline error", expanded=False):
            st.code(str(latest_error.get("error") or ""))


def _render_workspace_dashboard() -> None:
    _render_pipeline_status_bar()
    _render_pipeline_readiness_block()
    _render_global_run_monitor()
    _render_global_run_timeline()


def _path_exists_safely(value: str) -> bool:
    try:
        return bool(value) and Path(value).exists()
    except OSError:
        return False


def _compact_value_label(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if _path_exists_safely(normalized):
        path = Path(normalized)
        return path.name or str(path)
    if len(normalized) > 42:
        return f"{normalized[:39]}..."
    return normalized


def _handoff_sidebar_item(label: str, value: str, help_text: str) -> dict[str, str]:
    normalized = str(value or "").strip()
    if _path_exists_safely(normalized):
        status = "ready"
        detail = str(Path(normalized))
    elif normalized:
        status = "set"
        detail = normalized
    else:
        status = "missing"
        detail = help_text
    return {
        "label": label,
        "status": status,
        "summary": _compact_value_label(detail),
        "detail": detail,
    }


def _render_handoff_sidebar_group(title: str, items: list[dict[str, str]]) -> None:
    ready_count = sum(1 for item in items if item["status"] in {"ready", "set"})
    missing_count = len(items) - ready_count
    st.caption(f"{title}: {ready_count}/{len(items)} ready, {missing_count} missing")

    if not items:
        return

    with st.expander(f"{title} details", expanded=False):
        for item in items:
            prefix = "[missing]" if item["status"] == "missing" else "[ready]"
            summary = item["summary"]
            if summary:
                st.caption(f"{prefix} {item['label']}: {summary}")
            else:
                st.caption(f"{prefix} {item['label']}")


def _render_handoff_status_sidebar() -> None:
    st.subheader("Handoff Status")
    if st.button("Open readiness fixes", key="workspace_open_readiness_fixes", width="stretch"):
        _navigate_to("Overview")

    handoff = workspace_handoff_state(st.session_state)
    handoff_items = [
        _handoff_sidebar_item("Story -> Audio", _story_plain_display_value(), "No plain script is ready to send to Audio."),
        _handoff_sidebar_item("Story -> Image", handoff.story_image_handoff_dir, "No image prompt bundle is available from Story."),
        _handoff_sidebar_item("Story -> Video", handoff.story_video_handoff_dir, "No Story bundle is available for Video."),
        _handoff_sidebar_item("Audio -> Video", handoff.audio_output_path, "No audio output is ready to send to Video."),
        _handoff_sidebar_item("Audio subtitle", handoff.audio_srt_path, "No subtitle (.srt) is available from Audio."),
        _handoff_sidebar_item("Image cover", handoff.image_cover_path, "No cover image is available from Image handoff."),
        _handoff_sidebar_item("Image scenes", handoff.image_scenes_dir, "No scene images directory is available from Image handoff."),
        _handoff_sidebar_item("Image manifest", handoff.image_manifest_path, "No image manifest is available for Video/Image review."),
    ]
    _render_handoff_sidebar_group("Handoffs", handoff_items)

    outputs = workspace_source_outputs(st.session_state)
    output_items = [
        _handoff_sidebar_item("Story output", outputs.story_plain_script_path, "No recent Story output is available."),
        _handoff_sidebar_item("Audio output", outputs.audio_output, "No recent audio output is available."),
        _handoff_sidebar_item("Audio SRT", outputs.audio_srt_output, "No recent subtitle output is available."),
        _handoff_sidebar_item("Image cover output", outputs.image_cover_output, "No recent cover output is available."),
        _handoff_sidebar_item("Image scenes output", outputs.image_scenes_dir, "No recent scene images output is available."),
        _handoff_sidebar_item("Video output", outputs.video_output, "No recent video output is available."),
    ]
    _render_handoff_sidebar_group("Latest outputs", output_items)


def render_workspace_shell(
    *,
    title: str,
    caption: str,
    overview_renderer: OverviewRenderer,
    app_renderers: dict[str, Callable[[], None]],
) -> None:
    st.set_page_config(
        page_title=title,
        page_icon=":material/tune:",
        layout="wide",
        initial_sidebar_state=_workspace_sidebar_initial_state(),
    )
    ensure_workspace_shell_state()
    sync_pipeline_handoff_state()

    options = ["Overview", *app_renderers.keys()]
    _apply_pending_navigation_before_widgets(options)

    if not st.session_state.get(WORKSPACE_SIDEBAR_EXPANDED_KEY, True):
        if st.button(
            ":material/left_panel_open: Open sidebar",
            key="workspace_sidebar_expand_button",
            help="Expand the workspace sidebar",
        ):
            _expand_workspace_sidebar()

    with st.sidebar:
        title_cols = st.columns([1.0, 0.22])
        title_cols[0].header("Workspace")
        if title_cols[1].button(
            ":material/left_panel_close:",
            key="workspace_sidebar_collapse_button",
            help="Collapse sidebar",
            width="stretch",
        ):
            _collapse_workspace_sidebar()
        navigation = workspace_navigation_state(st.session_state)
        current = navigation.active_app
        if current not in options:
            current = "Overview"
            navigation.active_app = "Overview"

        if not navigation.active_app_selector:
            navigation.active_app_selector = current

        selection = st.radio(
            "Studio section",
            options=options,
            key="workspace_active_app_selector",
            help="Shared workspace shell for the pipeline: Story -> Audio / Image -> Video.",
        )

        navigation.active_app = selection

        _render_handoff_status_sidebar()

        st.divider()
        with st.expander("Runtime", expanded=False):
            runtime_slot = st.empty()
            set_runtime_usage_container(runtime_slot)
            render_runtime_usage_compact(container=runtime_slot)

    st.title(title)
    st.caption(caption)

    if selection == "Overview":
        _render_workspace_dashboard()
        overview_renderer()
        return

    renderer = app_renderers[selection]
    renderer()

    st.divider()
    show_dashboard = st.checkbox(
        "Show pipeline dashboard",
        key="workspace_show_pipeline_dashboard",
        help="Show readiness, global run monitor, and timeline below the current workspace.",
    )
    if show_dashboard:
        _render_workspace_dashboard()


def render_studio_shell(*args, **kwargs):
    return render_workspace_shell(*args, **kwargs)
