from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Optional

import streamlit as st

from video.app_api import RenderVideoRequest, VideoQualityGateError
from video.error_handling import (
    USER_FACING_EXCEPTIONS,
    format_unexpected_error,
    format_user_facing_error,
)
from video.ffmpeg_runner import get_media_duration_seconds
from video.gui.diagnostics_blocks import render_runtime_diagnostics_block
from video.gui.history_utils import append_capped_history_entry
from video.gui.panel_utils import (
    normalize_optional_path,
    render_download_button_from_path,
    render_json_summary_expander,
    render_session_history,
)
from video.gui.progress_details import format_progress_text
from video.gui.runtime_usage import render_runtime_usage_compact
from video.gui.service import run_video_job
from video.gui.shared_state import (
    append_global_run_event,
    get_workspace_target_field,
    set_video_handoff,
    update_global_run_monitor,
)
from video.gui.state import ensure_session_defaults, video_session
from video.gui.user_messages import show_missing_input
from video.gui.view_models import build_video_run_summary
from video.gui.workspace_handoff import workspace_handoff_state
from video.gui.workspace_source_outputs import workspace_source_outputs
from video.handoff import read_audio_handoff
from video.runtime_tools import collect_runtime_diagnostics
from video.slideshow_concat import (
    append_outro_segment,
    build_slideshow_segments,
    prepend_cover_segment,
)
from video.validation import (
    ImageReadinessReport,
    autodetect_subtitle_from_audio,
    build_zone_slideshow_images,
    collect_scene_images,
    inspect_video_image_readiness,
    resolve_slideshow_cover,
    resolve_slideshow_outro,
)
from video.zone_timeline import ZoneSegment, build_zone_segments


def _existing_picker_directory(path_value: str) -> str:
    candidate = Path(str(path_value or "").strip()).expanduser()
    if candidate.is_file():
        return str(candidate.parent)
    if candidate.is_dir():
        return str(candidate)
    for parent in candidate.parents:
        if parent.is_dir():
            return str(parent)
    return str(Path.cwd())


def _choose_local_path(*, state_key: str, directory: bool) -> None:
    root = None
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial_dir = _existing_picker_directory(str(st.session_state.get(state_key) or ""))
        if directory:
            selected = filedialog.askdirectory(parent=root, initialdir=initial_dir, mustexist=True)
        else:
            selected = filedialog.askopenfilename(
                parent=root,
                initialdir=initial_dir,
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                    ("All files", "*.*"),
                ],
            )
        if selected:
            st.session_state[state_key] = selected
        st.session_state.pop("video_path_picker_error", None)
    except Exception as exc:
        st.session_state["video_path_picker_error"] = f"Could not open the path picker: {exc}"
    finally:
        if root is not None:
            root.destroy()


def validate_runtime_settings(*, ffmpeg_exe: str, ffprobe_exe: str) -> list[str]:
    errors: list[str] = []
    if not str(ffmpeg_exe or "").strip():
        errors.append("ffmpeg executable must not be empty.")
    if not str(ffprobe_exe or "").strip():
        errors.append("ffprobe executable must not be empty.")
    return errors


def validate_inputs(
    *,
    audio: Optional[Path],
    output: Optional[Path],
    mode: str,
    cover: Optional[Path],
    scenes_dir: Optional[Path],
    subtitle: Optional[Path],
    story_json: Optional[Path],
    zone_aware_slideshow: bool = False,
) -> list[str]:
    errors: list[str] = []
    if audio is None:
        errors.append("Enter an Audio file.")
    elif not audio.is_file():
        errors.append(f"Audio file not found: {audio}")

    if subtitle is not None and not subtitle.is_file():
        errors.append(f"Subtitle file not found: {subtitle}")

    if story_json is not None and not story_json.is_file():
        errors.append(f"story.json not found: {story_json}")

    if mode == "static":
        if cover is None:
            errors.append("Static mode requires a cover image or an asset profile with default_cover.")
        elif not cover.is_file():
            errors.append(f"Cover image not found: {cover}")

    if mode == "slideshow":
        if scenes_dir is None:
            errors.append(
                "Slideshow mode requires a scenes directory or an asset profile with default_scenes_dir."
            )
        elif not scenes_dir.is_dir():
            errors.append(f"Scenes directory not found: {scenes_dir}")
        if zone_aware_slideshow:
            if story_json is None:
                errors.append("Zone-aware slideshow requires a story.json file.")
            if subtitle is None:
                errors.append("Zone-aware slideshow requires a subtitle .srt file with timestamps.")

    if output is None:
        errors.append("Enter an output MP4 path.")
    else:
        parent = output.parent
        if str(parent) and not parent.exists():
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                errors.append(f"Could not create output directory {parent}: {exc}")

    return errors


def _image_readiness_rows(report: ImageReadinessReport) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset in report.assets:
        rows.append(
            {
                "role": asset.role,
                "status": asset.level,
                "file": asset.path.name,
                "zone": asset.zone or "",
                "size": f"{asset.width}x{asset.height}" if asset.width and asset.height else "",
                "detail": asset.message,
            }
        )
    return rows


def _image_readiness_summary(report: ImageReadinessReport) -> dict[str, Any]:
    return {
        "ready": report.ready,
        "expected_resolution": f"{report.expected_width}x{report.expected_height}",
        "scene_count": report.scene_count,
        "mapped_zones": list(report.mapped_zones),
        "missing_zones": list(report.missing_zones),
        "unmatched_files": [path.name for path in report.unmatched_files],
        "errors": report.errors,
        "warnings": report.warnings,
    }


def _extend_unique(items: list[str], additions: list[str]) -> None:
    for addition in additions:
        if addition not in items:
            items.append(addition)


def _render_image_readiness_report(report: ImageReadinessReport) -> None:
    if report.ready and not report.warnings:
        st.success("Images are ready for video render.")
    elif report.ready:
        st.warning("Images can be rendered, but there are warnings to review.")
    else:
        st.error("Images are not ready for video render.")

    if report.errors:
        for error in report.errors:
            st.error(error)
    if report.warnings:
        for warning in report.warnings:
            st.warning(warning)

    rows = _image_readiness_rows(report)
    if rows:
        st.dataframe(rows, width="stretch", height=min(360, 80 + len(rows) * 36))
    render_json_summary_expander(
        "Image readiness summary",
        _image_readiness_summary(report),
        expanded=False,
    )


def _guess_mp4_output_from_audio(audio_path: str, output_dir: str) -> str:
    raw = (audio_path or "").strip()
    if raw:
        audio_file = Path(raw)
        return str(Path(output_dir) / f"{audio_file.stem}.mp4")
    return str(Path(output_dir) / "video.mp4")


def default_scenes_directory(input_root: str, aspect: str) -> str:
    directory = "landscape" if aspect == "16x9" else "portrait"
    return str(Path(input_root or "output") / directory)


def default_cover_path(input_root: str, aspect: str) -> str:
    return str(Path(default_scenes_directory(input_root, aspect)) / "cover.png")


def default_video_output(output_dir: str, aspect: str) -> str:
    filename = "video_landscape.mp4" if aspect == "16x9" else "video_portrait.mp4"
    return str(Path(output_dir or "output") / filename)


def should_update_scenes_directory(
    *, mode: str, current: str, suggested: str, previous_suggestion: str
) -> bool:
    replaceable_defaults = {
        "",
        previous_suggestion,
        "input/scene_images",
        "output/landscape",
        "output/portrait",
    }
    return mode == "slideshow" and current in replaceable_defaults and current != suggested


def should_update_cover_path(
    *, mode: str, current: str, suggested: str, previous_suggestion: str
) -> bool:
    replaceable_defaults = {
        "",
        previous_suggestion,
        "input/cover.png",
        "output/cover.png",
        "output/landscape/cover.png",
        "output/portrait/cover.png",
    }
    return mode == "slideshow" and current in replaceable_defaults and current != suggested


def should_update_video_output(
    *, mode: str, current: str, suggested: str, previous_suggestion: str
) -> bool:
    replaceable_defaults = {
        "",
        previous_suggestion,
        "output/video.mp4",
        "output/video_landscape.mp4",
        "output/video_portrait.mp4",
    }
    return mode == "slideshow" and current in replaceable_defaults and current != suggested


def _apply_audio_handoff_prefill(settings: dict[str, Any]) -> None:
    handoff = workspace_handoff_state(st.session_state)
    incoming_audio = handoff.audio_output_path
    incoming_srt = handoff.audio_srt_path

    session = video_session()
    prev_audio = session.auto_audio_input
    prev_srt = session.auto_subtitle_input
    prev_output = session.auto_output_input
    lock_to_handoff = session.lock_to_audio_handoff

    if incoming_audio and incoming_audio != prev_audio:
        current_audio = st.session_state.get("video_audio_input", "") or ""
        if lock_to_handoff or not current_audio or current_audio == prev_audio:
            session.audio_input = incoming_audio
        suggested_output = _guess_mp4_output_from_audio(incoming_audio, settings["output_dir"])
        current_output = st.session_state.get("video_output_input", "") or ""
        if lock_to_handoff or not current_output or current_output == prev_output:
            session.output_input = suggested_output
            session.auto_output_input = suggested_output
        session.auto_audio_input = incoming_audio

    if incoming_srt and incoming_srt != prev_srt:
        current_srt = st.session_state.get("video_subtitle_input", "") or ""
        if lock_to_handoff or not current_srt or current_srt == prev_srt:
            session.subtitle_input = incoming_srt
        session.auto_subtitle_input = incoming_srt


def _ensure_video_input_defaults(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    st.session_state.setdefault("video_cover_input", "")
    st.session_state.setdefault("video_scenes_input", "")
    st.session_state.setdefault("video_story_json_input", "")
    st.session_state.setdefault("video_audio_handoff_manifest", "")
    input_root = str(settings.get("input_root") or "output")
    aspect = str(settings.get("aspect") or "16x9")

    suggested_cover = default_cover_path(input_root, aspect)
    previous_cover_suggestion = str(st.session_state.get("video_auto_cover_path") or "")
    current_cover = str(st.session_state.get("video_input_cover_path") or "").strip()
    if should_update_cover_path(
        mode=str(settings.get("mode") or ""),
        current=current_cover,
        suggested=suggested_cover,
        previous_suggestion=previous_cover_suggestion,
    ):
        st.session_state["video_input_cover_path"] = suggested_cover
        st.session_state["video_auto_cover_path"] = suggested_cover
    else:
        st.session_state.setdefault("video_input_cover_path", suggested_cover)

    suggested_scenes = default_scenes_directory(input_root, aspect)
    previous_suggestion = str(st.session_state.get("video_auto_scenes_dir") or "")
    current_scenes = str(st.session_state.get("video_input_scenes_dir") or "").strip()
    if should_update_scenes_directory(
        mode=str(settings.get("mode") or ""),
        current=current_scenes,
        suggested=suggested_scenes,
        previous_suggestion=previous_suggestion,
    ):
        st.session_state["video_input_scenes_dir"] = suggested_scenes
        st.session_state["video_auto_scenes_dir"] = suggested_scenes
    else:
        st.session_state.setdefault("video_input_scenes_dir", suggested_scenes)

    suggested_output = default_video_output(str(settings.get("output_dir") or "output"), aspect)
    previous_output_suggestion = str(st.session_state.get("video_auto_output_path") or "")
    current_output = str(st.session_state.get("video_output_input") or "").strip()
    if should_update_video_output(
        mode=str(settings.get("mode") or ""),
        current=current_output,
        suggested=suggested_output,
        previous_suggestion=previous_output_suggestion,
    ):
        st.session_state["video_output_input"] = suggested_output
        st.session_state["video_auto_output_path"] = suggested_output
    else:
        st.session_state.setdefault("video_output_input", suggested_output)

def _resolve_cover_path(settings: dict[str, Any]) -> Optional[Path]:
    del settings
    return normalize_optional_path(str(st.session_state.get("video_input_cover_path") or ""))


def _resolve_scenes_dir(settings: dict[str, Any]) -> Optional[Path]:
    del settings
    return normalize_optional_path(str(st.session_state.get("video_input_scenes_dir") or ""))


def _prepare_video_inputs(settings: dict[str, Any]) -> None:
    _apply_audio_handoff_prefill(settings)
    _ensure_video_input_defaults(settings)


def _autodetect_story_json(settings: dict[str, Any], audio_path: Optional[Path]) -> Optional[Path]:
    candidates: list[Path] = []
    if audio_path is not None:
        candidates.extend(
            [
                audio_path.with_suffix(".json"),
                audio_path.parent / "story.json",
                audio_path.parent / "story" / "story.json",
            ]
        )
    input_root = Path(str(settings.get("input_root") or ""))
    if str(input_root):
        candidates.extend([input_root / "story.json", input_root / "story" / "story.json"])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _collect_inputs(settings: dict[str, Any]) -> dict[str, Any]:
    _prepare_video_inputs(settings)

    audio_raw = str(st.session_state.get("video_audio_input") or "").strip()
    output_raw = str(st.session_state.get("video_output_input") or "").strip()

    audio_path = Path(audio_raw) if audio_raw else None
    output_path = Path(output_raw) if output_raw else None

    subtitle_path = normalize_optional_path(st.session_state.get("video_subtitle_input") or "")
    if subtitle_path is None and audio_path is not None:
        subtitle_path = autodetect_subtitle_from_audio(audio_path)
    story_json_path = normalize_optional_path(st.session_state.get("video_story_json_input") or "")
    if story_json_path is None:
        story_json_path = _autodetect_story_json(settings, audio_path)
    cover_path = _resolve_cover_path(settings)
    scenes_dir = _resolve_scenes_dir(settings)
    if str(settings["mode"]) == "slideshow":
        cover_path = resolve_slideshow_cover(
            cover_path,
            scenes_dir,
            cover_first=bool(settings.get("cover_first", True)),
        )
    image_readiness = inspect_video_image_readiness(
        mode=str(settings["mode"]),
        aspect=str(settings["aspect"]),
        cover=cover_path,
        scenes_dir=scenes_dir,
        cover_first=bool(settings.get("cover_first", True)),
        outro_last=bool(settings.get("outro_last", True)),
    )

    errors = validate_inputs(
        audio=audio_path,
        output=output_path,
        mode=str(settings["mode"]),
        cover=cover_path,
        scenes_dir=scenes_dir,
        subtitle=subtitle_path,
        story_json=story_json_path,
        zone_aware_slideshow=bool(settings.get("zone_aware_slideshow")),
    )

    errors.extend(
        validate_runtime_settings(
            ffmpeg_exe=str(settings["ffmpeg_exe"]),
            ffprobe_exe=str(settings["ffprobe_exe"]),
        )
    )
    _extend_unique(errors, image_readiness.errors)
    summary = build_video_run_summary(
        audio=audio_path,
        output=output_path,
        subtitle=subtitle_path,
        story_json=story_json_path,
        cover=cover_path,
        scenes_dir=scenes_dir,
        settings=settings,
    )
    summary["cover_source"] = "input"
    summary["scenes_source"] = "input"
    summary["image_readiness"] = _image_readiness_summary(image_readiness)
    return {
        "audio": audio_path,
        "output": output_path,
        "cover": cover_path,
        "scenes_dir": scenes_dir,
        "subtitle": subtitle_path,
        "story_json": story_json_path,
        "image_readiness": image_readiness,
        "errors": errors,
        "summary": summary,
    }


def _append_history(summary: dict[str, Any]) -> None:
    output_path = Path(summary.get("output") or "") if summary.get("output") else None
    append_capped_history_entry(
        "video_run_history",
        {
            "output": str(output_path) if output_path else "",
            "output_name": output_path.name if output_path else "",
            "mode": summary.get("mode"),
            "aspect": summary.get("aspect"),
        },
        limit=12,
    )



def render_doctor_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    st.subheader("Doctor")
    st.caption("Check Video runtime, input, and image readiness.")
    _prepare_video_inputs(settings)
    diagnostics = collect_runtime_diagnostics(
        ffmpeg_exe=str(settings.get("ffmpeg_exe") or ""),
        ffprobe_exe=str(settings.get("ffprobe_exe") or ""),
    )
    cover_path = _resolve_cover_path(settings)
    scenes_dir = _resolve_scenes_dir(settings)
    audio_path = normalize_optional_path(str(st.session_state.get("video_audio_input") or ""))
    subtitle_path = normalize_optional_path(str(st.session_state.get("video_subtitle_input") or ""))
    story_json_path = normalize_optional_path(str(st.session_state.get("video_story_json_input") or ""))
    if story_json_path is None:
        story_json_path = _autodetect_story_json(settings, audio_path)

    c1, c2, c3 = st.columns(3)
    c1.metric("Mode", str(settings.get("mode") or "-"))
    c2.metric("Asset source", "Direct input")
    c3.metric("Runtime tools", len(getattr(diagnostics, "tools", []) or []))

    rows = [
        {"check": "Audio input", "status": "OK" if audio_path and audio_path.is_file() else "missing", "detail": str(audio_path or "Audio input not set")},
        {"check": "Subtitle", "status": "OK" if subtitle_path and subtitle_path.is_file() else ("not set" if subtitle_path is None else "missing"), "detail": str(subtitle_path or "Leave empty for autodetect or optional subtitle")},
        {"check": "Timeline JSON", "status": "OK" if story_json_path and story_json_path.is_file() else ("not set" if story_json_path is None else "missing"), "detail": str(story_json_path or "Leave empty for autodetect or zone-aware slideshow")},
        {"check": "Cover", "status": "OK" if cover_path and cover_path.is_file() else "missing", "detail": str(cover_path or "Cover not set")},
        {"check": "Scenes dir", "status": "OK" if scenes_dir and scenes_dir.is_dir() else "missing", "detail": str(scenes_dir or "Scenes directory not set")},
    ]
    st.dataframe(rows, width="stretch", height=240)
    st.subheader("Image readiness")
    _render_image_readiness_report(
        inspect_video_image_readiness(
            mode=str(settings.get("mode") or ""),
            aspect=str(settings.get("aspect") or ""),
            cover=cover_path,
            scenes_dir=scenes_dir,
            cover_first=bool(settings.get("cover_first", True)),
            outro_last=bool(settings.get("outro_last", True)),
        )
    )
    render_runtime_diagnostics_block({
        "settings": {
            "mode": settings.get("mode"),
            "aspect": settings.get("aspect"),
            "duration_per_image": settings.get("duration_per_image"),
            "ffmpeg_exe": settings.get("ffmpeg_exe"),
            "ffprobe_exe": settings.get("ffprobe_exe"),
            "input_root": settings.get("input_root"),
            "output_dir": settings.get("output_dir"),
        },
        "resolved_inputs": {
            "audio": str(audio_path or ""),
            "subtitle": str(subtitle_path or ""),
            "story_json": str(story_json_path or ""),
            "cover": str(cover_path or ""),
            "scenes_dir": str(scenes_dir or ""),
        },
    }, label="Current Video settings", expanded=False)
    render_runtime_diagnostics_block(diagnostics, label="Raw runtime diagnostics", expanded=False, serializer=lambda info: info.as_dict())




def _render_video_focus_hint(view_name: str) -> None:
    if st.session_state.get("workspace_active_app") != "Video":
        return
    if st.session_state.get("video_embedded_view_selector") != view_name:
        return
    target_field = str(get_workspace_target_field("Video", "") or "").strip()
    if not target_field:
        return
    mapping = {
        "audio_input": "Audio file",
        "subtitle_input": "Subtitle file",
        "cover_input": "Cover image",
        "scenes_input": "Scenes directory",
        "manifest_input": "Image manifest / bundle assets",
        "video_output": "Video output",
        "doctor": "Video Doctor",
    }
    st.info(f"Deep-link target: {mapping.get(target_field, target_field)}")

def render_inputs_tab(settings: dict[str, Any]) -> None:
    _prepare_video_inputs(settings)

    st.subheader("Inputs")
    st.caption("Prepare and review the assets used by Video.")
    _render_video_focus_hint("inputs")
    st.checkbox(
        "Lock input to Audio handoff",
        key="video_lock_to_audio_handoff",
        help="When enabled, Video keeps following the newest audio/subtitle/output hints sent from Audio handoff.",
    )
    col_left, col_right = st.columns([1.15, 1.0])
    with col_left:
        st.text_input("Audio handoff manifest", key="video_audio_handoff_manifest")
        if st.button("Load audio handoff", key="video_load_audio_handoff", width="stretch"):
            try:
                audio_manifest = str(st.session_state.get("video_audio_handoff_manifest") or "").strip()
                if audio_manifest:
                    incoming_audio = read_audio_handoff(Path(audio_manifest))
                    st.session_state["video_audio_input"] = str(incoming_audio.audio)
                    st.session_state["video_subtitle_input"] = str(incoming_audio.subtitle or "")
                st.success("Loaded audio handoff. Direct asset inputs remain authoritative.")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                st.error(f"Could not load handoff manifest: {exc}")
        st.text_input("Audio file", key="video_audio_input")
        st.text_input(
            "Subtitle file (leave empty = autodetect from audio)",
            key="video_subtitle_input",
        )
        st.text_input(
            "Timeline JSON (leave empty = autodetect)",
            key="video_story_json_input",
        )
        st.text_input("Output MP4", key="video_output_input")
    with col_right:
        st.caption("Asset-driven inputs")
        cover_cols = st.columns([4.0, 1.35], vertical_alignment="bottom")
        cover_cols[0].text_input("Input cover image", key="video_input_cover_path")
        cover_cols[1].button(
            "Select file",
            key="video_select_cover_file",
            width="stretch",
            on_click=_choose_local_path,
            kwargs={"state_key": "video_input_cover_path", "directory": False},
        )

        scenes_cols = st.columns([4.0, 1.35], vertical_alignment="bottom")
        scenes_cols[0].text_input("Input scenes directory", key="video_input_scenes_dir")
        scenes_cols[1].button(
            "Select folder",
            key="video_select_scenes_directory",
            width="stretch",
            on_click=_choose_local_path,
            kwargs={"state_key": "video_input_scenes_dir", "directory": True},
        )

        if picker_error := st.session_state.get("video_path_picker_error"):
            st.error(str(picker_error))


    render_json_summary_expander("Run configuration summary", _collect_inputs(settings)["summary"], expanded=False)


def render_run_tab(settings: dict[str, Any]) -> None:
    st.subheader("Run")
    st.caption("Validate and render the current Video job.")
    inputs = _collect_inputs(settings)
    errors = inputs["errors"]
    if errors:
        for err in errors:
            show_missing_input("video input", hint=err, actions=["Check audio, subtitle, cover, scenes, and output path before rendering."])

    progress = st.progress(0.0, text=format_progress_text(0, "Not started", [f"mode={settings.get('mode')}", f"aspect={settings.get('aspect')}"]))
    status = st.empty()
    if st.button("Render video", type="primary", width="stretch", disabled=bool(errors)):
        update_global_run_monitor(
            app="Video",
            stage="Render",
            status="running",
            progress=10,
            summary=inputs["summary"],
        )
        append_global_run_event(
            app="Video",
            stage="Render",
            status="running",
            message=f"mode={settings.get('mode')} aspect={settings.get('aspect')}",
        )
        try:

            def callback(done: float, message: str = ""):
                frac = max(0.0, min(1.0, float(done) / 100.0))
                percent = int(round(frac * 100))
                detail_text = format_progress_text(
                    percent,
                    message or "Processing",
                    [f"mode={settings.get('mode')}", f"aspect={settings.get('aspect')}", f"output={inputs['output'].name if inputs.get('output') else '-'}"],
                )
                progress.progress(
                    frac, text=detail_text
                )
                render_runtime_usage_compact()
                update_global_run_monitor(
                    app="Video",
                    stage="Render",
                    status="running",
                    progress=percent,
                    summary=inputs["summary"],
                )

            result = run_video_job(
                RenderVideoRequest(
                    audio=inputs["audio"],
                    output=inputs["output"],
                    mode=settings["mode"],
                    aspect=settings["aspect"],
                    duration_per_image=settings["duration_per_image"],
                    subtitle=inputs["subtitle"],
                    show_subtitles=bool(settings.get("show_subtitles", True)),
                    story_json=inputs["story_json"],
                    cover=inputs["cover"],
                    scenes_dir=inputs["scenes_dir"],
                    cover_first=bool(settings.get("cover_first", True)),
                    cover_duration=float(settings.get("cover_duration", 3.0)),
                    outro_last=bool(settings.get("outro_last", True)),
                    outro_duration=float(settings.get("outro_duration", 5.0)),
                    ffmpeg_exe=settings["ffmpeg_exe"],
                    ffprobe_exe=settings["ffprobe_exe"],
                    video_codec=settings.get("video_codec"),
                    audio_codec=settings.get("audio_codec"),
                    audio_bitrate=settings.get("audio_bitrate"),
                    encoding_profile=settings.get("encoding_profile"),
                    loudness_profile=settings.get("loudness_profile"),
                    quality_gate=settings.get("quality_gate"),
                    video_preset=settings.get("video_preset"),
                    video_crf=settings.get("video_crf"),
                    video_fps=settings.get("video_fps"),
                    video_tune=settings.get("video_tune"),
                    video_movflags=settings.get("video_movflags"),
                    slideshow_match_audio=settings.get("slideshow_match_audio"),
                    zone_aware_slideshow=settings.get("zone_aware_slideshow"),
                    environment_overlays=bool(settings.get("environment_overlays", True)),
                    environment_overlay_intensity=str(settings.get("environment_overlay_intensity", "normal")),
                    environment_overlay_fade=float(settings.get("environment_overlay_fade", 0.6)),
                    environment_allow_lens_effects=bool(settings.get("environment_allow_lens_effects", True)),
                    environment_global_film_grain=float(settings.get("environment_global_film_grain", 0.0)),
                    audio_match_epsilon=settings.get("audio_match_epsilon"),
                    keep_concat_list=settings.get("keep_concat_list"),
                    subtitle_font=settings.get("subtitle_font"),
                    subtitle_font_size=settings.get("subtitle_font_size"),
                    subtitle_text_color=settings.get("subtitle_text_color"),
                    subtitle_text_opacity=settings.get("subtitle_text_opacity"),
                    subtitle_outline=settings.get("subtitle_outline"),
                    subtitle_shadow=settings.get("subtitle_shadow"),
                    subtitle_background_color=settings.get("subtitle_background_color"),
                    subtitle_background_opacity=settings.get("subtitle_background_opacity"),
                    subtitle_position=settings.get("subtitle_position"),
                    subtitle_alignment=settings.get("subtitle_alignment"),
                    subtitle_margin_l=settings.get("subtitle_margin_l"),
                    subtitle_margin_r=settings.get("subtitle_margin_r"),
                    subtitle_margin_v=settings.get("subtitle_margin_v"),
                    subtitle_force_style=settings.get("subtitle_force_style"),
                    ffmpeg_loglevel=settings.get("ffmpeg_loglevel"),
                    ffmpeg_stream_log=settings.get("ffmpeg_stream_log"),
                    ffmpeg_stats=settings.get("ffmpeg_stats"),
                    show_progress=settings.get("show_progress"),
                    stderr_tail_lines=settings.get("stderr_tail_lines"),
                    print_ffmpeg_version=settings.get("print_ffmpeg_version"),
                    debug_ffmpeg_exe=settings.get("debug_ffmpeg_exe"),
                    render_video_history_dir=settings.get("render_video_history_dir"),
                    render_video_history_file=settings.get("render_video_history_file"),
                ),
                progress_callback=callback,
            )
            st.session_state["video_last_summary"] = inputs["summary"]
            st.session_state["video_last_stdout"] = result["stdout"]
            st.session_state["video_last_stderr"] = result["stderr"]
            st.session_state["video_last_error"] = ""
            workspace_source_outputs(st.session_state).video_output = str(inputs["output"])
            st.session_state["video_last_result_history_file"] = result.get("history_file", "")
            st.session_state["video_last_quality_report"] = result.get("quality_report_path", "")
            set_video_handoff(video_output_path=workspace_source_outputs(st.session_state).video_output)
            update_global_run_monitor(
                app="Video",
                stage="Render",
                status="completed",
                progress=100,
                output_path=workspace_source_outputs(st.session_state).video_output,
                summary=inputs["summary"],
            )
            append_global_run_event(
                app="Video",
                stage="Render",
                status="completed",
                message=f"mode={settings.get('mode')} aspect={settings.get('aspect')}",
                output_path=workspace_source_outputs(st.session_state).video_output,
            )
            progress.progress(1.0, text=format_progress_text(100, "Complete", [f"mode={settings.get('mode')}", f"aspect={settings.get('aspect')}", f"output={inputs['output'].name if inputs.get('output') else '-'}"]))
            status.success("Video render completed successfully")
            _append_history(inputs["summary"])
        except VideoQualityGateError as exc:
            st.session_state["video_last_summary"] = inputs["summary"]
            st.session_state["video_last_stdout"] = ""
            st.session_state["video_last_stderr"] = ""
            st.session_state["video_last_error"] = ""
            st.session_state["video_last_result_history_file"] = ""
            st.session_state["video_last_quality_report"] = str(exc.report_path)
            workspace_source_outputs(st.session_state).video_output = str(exc.output_path)
            set_video_handoff(video_output_path=str(exc.output_path))
            failed_checks = ", ".join(exc.failed_checks)
            warning_message = (
                f"Video created successfully: {exc.output_path.name}. "
                f"Quality checks need review: {failed_checks}."
            )
            update_global_run_monitor(
                app="Video",
                stage="Render",
                status="completed",
                progress=100,
                output_path=str(exc.output_path),
                summary=inputs["summary"],
            )
            append_global_run_event(
                app="Video",
                stage="Render",
                status="completed",
                message=warning_message,
                output_path=str(exc.output_path),
            )
            progress.progress(
                1.0,
                text=format_progress_text(
                    100,
                    "Complete with quality warnings",
                    [
                        f"mode={settings.get('mode')}",
                        f"aspect={settings.get('aspect')}",
                        f"output={exc.output_path.name}",
                    ],
                ),
            )
            status.warning(warning_message)
            _append_history(inputs["summary"])
        except USER_FACING_EXCEPTIONS as exc:
            message = format_user_facing_error(exc)
            st.session_state["video_last_error"] = message
            update_global_run_monitor(
                app="Video",
                stage="Render",
                status="failed",
                progress=100,
                error_text=message,
                summary=inputs["summary"],
            )
            append_global_run_event(
                app="Video",
                stage="Render",
                status="failed",
                message="Video render failed",
                error_text=message,
            )
            status.error(message)
        except (RuntimeError, TypeError, AssertionError) as exc:
            st.session_state["video_last_error"] = f"{exc}\n\n{traceback.format_exc()}"
            unexpected_message = format_unexpected_error(exc)
            update_global_run_monitor(
                app="Video",
                stage="Render",
                status="failed",
                progress=100,
                error_text=st.session_state.get("video_last_error") or "",
                summary=inputs["summary"],
            )
            append_global_run_event(
                app="Video",
                stage="Render",
                status="failed",
                message="Video render failed",
                error_text=st.session_state.get("video_last_error") or "",
            )
            status.error(unexpected_message)

    if st.session_state.get("video_last_summary"):
        st.divider()
        st.subheader("Latest result")
        st.json(st.session_state.get("video_last_summary"))
        out = workspace_source_outputs(st.session_state).video_output
        if out and Path(out).is_file():
            st.video(out)
            out_path = Path(out)
            render_download_button_from_path("Download MP4", out_path, mime="video/mp4", file_name=out_path.name)
        quality_path = Path(str(st.session_state.get("video_last_quality_report") or ""))
        if quality_path.is_file():
            render_download_button_from_path(
                "Download Video Quality Report",
                quality_path,
                mime="application/json",
                file_name=quality_path.name,
            )



def _build_test_slideshow_segments(
    inputs: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[list[ZoneSegment], Optional[str]]:
    scenes_dir = inputs.get("scenes_dir")
    if scenes_dir is None or not Path(scenes_dir).is_dir():
        return [], None

    cover = resolve_slideshow_cover(
        inputs.get("cover"),
        Path(scenes_dir),
        cover_first=bool(settings.get("cover_first", True)),
    )
    outro = resolve_slideshow_outro(
        Path(scenes_dir),
        outro_last=bool(settings.get("outro_last", True)),
    )
    try:
        if bool(settings.get("zone_aware_slideshow")):
            story_json = inputs.get("story_json")
            subtitle = inputs.get("subtitle")
            if story_json and subtitle and Path(story_json).is_file() and Path(subtitle).is_file():
                segments = build_zone_segments(
                    timeline_json=Path(story_json),
                    subtitle=Path(subtitle),
                    scenes_dir=Path(scenes_dir),
                )
                segments = prepend_cover_segment(
                    segments,
                    cover if cover and Path(cover).is_file() else None,
                    float(settings.get("cover_duration", 3.0)),
                )
                return append_outro_segment(
                    segments,
                    outro,
                    float(settings.get("outro_duration", 5.0)),
                ), None

        images = build_zone_slideshow_images(collect_scene_images(Path(scenes_dir)))
        if cover is not None and Path(cover).is_file():
            cover_resolved = Path(cover).resolve(strict=False)
            images = [
                image for image in images if image.resolve(strict=False) != cover_resolved
            ]
        if outro is not None:
            outro_resolved = outro.resolve(strict=False)
            images = [
                image for image in images if image.resolve(strict=False) != outro_resolved
            ]
        if not images:
            return [], None
        audio = inputs.get("audio")
        audio_duration = (
            get_media_duration_seconds(Path(audio))
            if audio and Path(audio).is_file()
            else None
        )
        segments = build_slideshow_segments(
            images,
            float(settings.get("duration_per_image", 60.0)),
            audio_duration=audio_duration,
            match_audio=bool(settings.get("slideshow_match_audio", True)),
            audio_match_epsilon=float(settings.get("audio_match_epsilon", 0.2)),
        )
        segments = prepend_cover_segment(
            segments,
            cover if cover and Path(cover).is_file() else None,
            float(settings.get("cover_duration", 3.0)),
        )
        return append_outro_segment(
            segments,
            outro,
            float(settings.get("outro_duration", 5.0)),
        ), None
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return [], str(exc)


def _render_slideshow_order_gallery(
    inputs: dict[str, Any],
    settings: dict[str, Any],
) -> None:
    segments, error = _build_test_slideshow_segments(inputs, settings)
    st.subheader("Slideshow image order")
    if error:
        st.warning(f"Could not build the exact slideshow timeline: {error}")
    gallery_items = _build_slideshow_gallery_items(inputs, settings, segments)
    if not gallery_items:
        st.info("No slideshow images are available yet.")
        return

    st.caption(
        f"Configured image order: {len(gallery_items)} image(s); "
        f"{len(segments)} effective timeline segment(s)."
    )
    for row_start in range(0, len(gallery_items), 4):
        columns = st.columns(4)
        for offset, (image_path, image_segments) in enumerate(
            gallery_items[row_start : row_start + 4]
        ):
            index = row_start + offset + 1
            columns[offset].image(str(image_path), width=160)
            if image_segments:
                timing = ", ".join(
                    f"{segment.zone} · {segment.start:.1f}s–{segment.end:.1f}s"
                    for segment in image_segments
                )
            else:
                timing = "not visible with current timing"
            columns[offset].caption(f"#{index:02d} {image_path.name}\n{timing}")


def _build_slideshow_gallery_items(
    inputs: dict[str, Any],
    settings: dict[str, Any],
    segments: list[ZoneSegment],
) -> list[tuple[Path, list[ZoneSegment]]]:
    """List every configured image, including ones clipped out by endpoint timing."""
    scenes_dir = inputs.get("scenes_dir")
    if scenes_dir is None or not Path(scenes_dir).is_dir():
        return []

    scene_root = Path(scenes_dir)
    cover = resolve_slideshow_cover(
        inputs.get("cover"),
        scene_root,
        cover_first=bool(settings.get("cover_first", True)),
    )
    outro = resolve_slideshow_outro(
        scene_root,
        outro_last=bool(settings.get("outro_last", True)),
    )
    scene_images = build_zone_slideshow_images(collect_scene_images(scene_root))
    endpoint_paths = {
        path.resolve(strict=False)
        for path in (cover, outro)
        if path is not None and path.is_file()
    }
    scene_images = [
        image for image in scene_images if image.resolve(strict=False) not in endpoint_paths
    ]

    ordered_images: list[Path] = []
    if cover is not None and cover.is_file():
        ordered_images.append(cover)
    ordered_images.extend(scene_images)
    if outro is not None and outro.is_file():
        ordered_images.append(outro)

    segments_by_image: dict[Path, list[ZoneSegment]] = {}
    for segment in segments:
        key = segment.image.resolve(strict=False)
        segments_by_image.setdefault(key, []).append(segment)
    return [
        (image, segments_by_image.get(image.resolve(strict=False), []))
        for image in ordered_images
    ]


def _render_slideshow_endpoint(
    *,
    title: str,
    status: str,
    message: str,
    image_path: Path | None,
    image_caption: str,
    details: dict[str, Any],
) -> None:
    """Render opening and ending settings with the same visual structure."""
    st.subheader(title)
    getattr(st, status)(message)
    if image_path is not None and image_path.is_file():
        image_column, details_column = st.columns([1, 2], gap="large")
        with image_column:
            st.image(str(image_path), caption=image_caption, width=320)
        with details_column:
            st.write(details)
    else:
        st.write(details)


def _render_test_media_inputs(inputs: dict[str, Any], summary: dict[str, Any]) -> None:
    """Render resolved test inputs around the audio preview without raw JSON blocks."""
    st.subheader("Audio & resolved inputs")
    audio_path = inputs.get("audio")
    if audio_path and Path(audio_path).is_file():
        st.audio(str(audio_path))
    else:
        st.info("No playable audio input is available yet.")

    rows = []
    for label, key, source_key in (
        ("Audio", "audio", None),
        ("Subtitle", "subtitle", None),
        ("Timeline JSON", "story_json", None),
        ("Video output", "output", None),
        ("Cover", "cover", "cover_source"),
        ("Scenes", "scenes_dir", "scenes_source"),
    ):
        value = inputs.get(key)
        path = Path(value) if value else None
        exists = bool(path and path.exists())
        rows.append(
            {
                "input": label,
                "status": "ready" if exists else ("pending" if key == "output" else "missing"),
                "file": path.name if path else "",
                "source": str(summary.get(source_key) or "") if source_key else "",
                "path": str(path or ""),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True, height=250)


def render_test_tab(settings: dict[str, Any]) -> None:
    st.subheader("Test")
    st.caption("Resolve inputs and preview the effective Video plan.")
    inputs = _collect_inputs(settings)
    summary = dict(inputs.get("summary") or {})

    if inputs.get("errors"):
        for err in inputs["errors"]:
            show_missing_input("video input", hint=err, actions=["Check the selected source again in the Inputs tab."])
    else:
        st.success("Current video inputs resolve successfully.")

    _render_test_media_inputs(inputs, summary)

    st.subheader("Image readiness")
    _render_image_readiness_report(inputs["image_readiness"])

    is_slideshow = str(settings.get("mode") or "") == "slideshow"
    scenes_dir = inputs.get("scenes_dir")
    if is_slideshow and scenes_dir and Path(scenes_dir).is_dir():
        _render_slideshow_order_gallery(inputs, settings)

    if is_slideshow:
        cover_first = bool(settings.get("cover_first", True))
        cover_duration = float(settings.get("cover_duration", 3.0))
        cover_path = Path(inputs["cover"]) if inputs.get("cover") else None
        cover_available = bool(cover_path and cover_path.is_file())
        if not cover_first:
            opening_status = "info"
            opening_message = "Cover-first is disabled. The video will start with the first scene image."
        elif cover_available:
            opening_status = "success"
            opening_message = (
                f"Cover-first is active: {cover_path.name} will be shown for "
                f"{cover_duration:g} seconds without extending the MP4 duration."
            )
        else:
            opening_status = "warning"
            opening_message = (
                "Cover-first is enabled, but the selected cover is unavailable. "
                "The video will start with the first scene image."
            )
        _render_slideshow_endpoint(
            title="Slideshow opening",
            status=opening_status,
            message=opening_message,
            image_path=cover_path if cover_first and cover_available else None,
            image_caption=f"Opening cover: {cover_path.name}" if cover_path else "Opening cover",
            details={
                "cover_first": cover_first,
                "cover_duration_seconds": cover_duration,
                "cover_path": str(cover_path or ""),
                "effective_first_image": (
                    str(cover_path)
                    if cover_first and cover_available
                    else str(inputs.get("scenes_dir") or "")
                ),
            },
        )

        outro_last = bool(settings.get("outro_last", True))
        outro_duration = float(settings.get("outro_duration", 5.0))
        outro_path = resolve_slideshow_outro(
            inputs.get("scenes_dir"),
            outro_last=outro_last,
        )
        if not outro_last:
            ending_status = "info"
            ending_message = "End screen is disabled. The video will keep its final scene."
        elif outro_path is not None:
            ending_status = "success"
            ending_message = (
                f"End screen is active: {outro_path.name} will be shown for "
                f"the final {outro_duration:g} seconds without extending the MP4 duration."
            )
        else:
            ending_status = "warning"
            ending_message = (
                "End screen is enabled, but outro.png was not found. "
                "The video will keep its final scene."
            )
        _render_slideshow_endpoint(
            title="Slideshow ending",
            status=ending_status,
            message=ending_message,
            image_path=outro_path,
            image_caption=f"End screen: {outro_path.name}" if outro_path else "End screen",
            details={
                "outro_last": outro_last,
                "outro_duration_seconds": outro_duration,
                "outro_path": str(outro_path or ""),
                "effective_last_image": str(outro_path or ""),
            },
        )

    cover_path = inputs.get("cover")
    if not is_slideshow and cover_path and Path(cover_path).is_file():
        cover_caption = Path(cover_path).name
        st.image(str(cover_path), caption=cover_caption, width=240)

    render_json_summary_expander("Test input summary", summary, expanded=False)

def render_preview_logs_tab(settings: dict[str, Any]) -> None:
    del settings
    st.subheader("Results & Logs")
    st.caption("Inspect the latest Video output and runtime logs.")
    out = workspace_source_outputs(st.session_state).video_output
    if out and Path(out).is_file():
        st.video(out)
    if st.session_state.get("video_last_stdout"):
        st.subheader("stdout")
        st.code(st.session_state.get("video_last_stdout") or "")
    if st.session_state.get("video_last_stderr"):
        st.subheader("stderr")
        st.code(st.session_state.get("video_last_stderr") or "")
    if st.session_state.get("video_last_result_history_file"):
        st.caption(f"History file: {st.session_state.get('video_last_result_history_file') or ''}")
    if st.session_state.get("video_last_error"):
        st.subheader("error")
        st.code(st.session_state.get("video_last_error") or "")


def render_history_tab(settings: dict[str, Any]) -> None:
    del settings
    st.subheader("History")
    st.caption("Review Video renders from the current session.")
    items = st.session_state.get("video_run_history", [])
    render_session_history(
        items,
        empty_message="No render history is available in the current session.",
        title_builder=lambda idx, item: f"#{idx} | {item.get('output_name') or item.get('output') or 'video'}",
    )
