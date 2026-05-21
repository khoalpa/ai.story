from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Optional

import streamlit as st

from common.gui.diagnostics_blocks import render_runtime_diagnostics_block
from common.gui.history_utils import append_capped_history_entry
from common.gui.panel_utils import (
    normalize_optional_path,
    render_download_button_from_path,
    render_json_summary_expander,
    render_session_history,
)
from common.gui.state import append_global_run_event, get_workspace_target_field, set_video_handoff, update_global_run_monitor
from common.gui.progress_details import format_progress_text
from common.gui.runtime_usage import render_runtime_usage_compact
from common.gui.workspace_handoff import workspace_handoff_state
from common.gui.workspace_source_outputs import workspace_source_outputs
from common.gui.user_messages import show_missing_input, show_provider_error
from video.app_api import RenderVideoRequest
from video.error_handling import (
    USER_FACING_EXCEPTIONS,
    format_unexpected_error,
    format_user_facing_error,
)
from video.gui.service import run_video_job
from video.gui.state import ensure_session_defaults, video_session
from video.gui.view_models import build_video_run_summary
from video.runtime_tools import collect_runtime_diagnostics
from video.validation import autodetect_subtitle_from_audio


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
) -> list[str]:
    errors: list[str] = []
    if audio is None:
        errors.append("Enter an Audio file.")
    elif not audio.is_file():
        errors.append(f"Audio file not found: {audio}")

    if subtitle is not None and not subtitle.is_file():
        errors.append(f"Subtitle file not found: {subtitle}")

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


def _guess_mp4_output_from_audio(audio_path: str, output_dir: str) -> str:
    raw = (audio_path or "").strip()
    if raw:
        audio_file = Path(raw)
        return str(Path(output_dir) / f"{audio_file.stem}.mp4")
    return str(Path(output_dir) / "story.mp4")


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


def _apply_image_handoff_prefill(settings: dict[str, Any]) -> None:
    del settings
    handoff = workspace_handoff_state(st.session_state)
    incoming_cover = handoff.image_cover_path
    incoming_scenes = handoff.image_scenes_dir
    session = video_session()
    prev_cover = session.auto_cover_input
    prev_scenes = session.auto_scenes_input
    lock_to_handoff = session.lock_to_image_handoff

    if incoming_cover and incoming_cover != prev_cover:
        current_cover = st.session_state.get("video_cover_input", "") or ""
        if lock_to_handoff or not current_cover or current_cover == prev_cover:
            session.cover_input = incoming_cover
        session.auto_cover_input = incoming_cover

    if incoming_scenes and incoming_scenes != prev_scenes:
        current_scenes = st.session_state.get("video_scenes_input", "") or ""
        if lock_to_handoff or not current_scenes or current_scenes == prev_scenes:
            session.scenes_input = incoming_scenes
        session.auto_scenes_input = incoming_scenes


def _load_story_bundle_manifest(bundle_dir: Path) -> dict[str, Any]:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found in bundle: {bundle_dir}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _import_story_bundle_into_video(bundle_dir: Path, settings: dict[str, Any]) -> dict[str, str]:
    manifest = _load_story_bundle_manifest(bundle_dir)
    scene_dir = bundle_dir / str(manifest.get("scene_images_dir") or "scene_images")
    cover_path = bundle_dir / str((manifest.get("cover_prompt") or {}).get("expected_image_file") or "cover.png")

    changes: dict[str, str] = {
        "story_bundle": str(bundle_dir),
        "manifest": str(bundle_dir / "manifest.json"),
        "scenes_dir": str(scene_dir),
        "cover": str(cover_path),
    }

    st.session_state["video_cover_source"] = "handoff"
    st.session_state["video_scenes_source"] = "handoff"
    st.session_state["video_cover_input"] = str(cover_path)
    st.session_state["video_scenes_input"] = str(scene_dir)
    if not str(st.session_state.get("video_output_input") or "").strip():
        st.session_state["video_output_input"] = str(Path(settings.get("output_dir") or "output") / "story.mp4")
    workspace_handoff_state(st.session_state).story_video_handoff_dir = str(bundle_dir)
    workspace_handoff_state(st.session_state).image_manifest_path = str(bundle_dir / "manifest.json")
    if cover_path.exists():
        workspace_handoff_state(st.session_state).image_cover_path = str(cover_path)
    if scene_dir.exists():
        workspace_handoff_state(st.session_state).image_scenes_dir = str(scene_dir)
    return changes


def _ensure_video_input_defaults(settings: dict[str, Any]) -> None:
    defaults = settings["defaults"]
    ensure_session_defaults()
    st.session_state.setdefault("video_cover_input", "")
    st.session_state.setdefault("video_scenes_input", "")
    st.session_state.setdefault("video_cover_source", "handoff")
    st.session_state.setdefault("video_scenes_source", "handoff")
    st.session_state.setdefault("video_input_cover_path", str(Path(settings.get("input_root") or "input") / "cover.png"))
    st.session_state.setdefault("video_input_scenes_dir", str(Path(settings.get("input_root") or "input") / "scene_images"))

    current_output = str(st.session_state.get("video_output_input") or "").strip()
    if not current_output:
        st.session_state["video_output_input"] = str(Path(settings["output_dir"]) / "story.mp4")

    current_cover = str(st.session_state.get("video_cover_input") or "").strip()
    if not current_cover and defaults.get("cover") is not None:
        st.session_state["video_cover_input"] = str(defaults["cover"])

    current_scenes = str(st.session_state.get("video_scenes_input") or "").strip()
    if not current_scenes and defaults.get("scenes_dir") is not None:
        st.session_state["video_scenes_input"] = str(defaults["scenes_dir"])


def _resolve_cover_path(settings: dict[str, Any]) -> Optional[Path]:
    source = str(st.session_state.get("video_cover_source") or "handoff").strip().lower()
    defaults = settings["defaults"]
    if source == "handoff":
        return normalize_optional_path(workspace_handoff_state(st.session_state).image_cover_path or str(st.session_state.get("video_cover_input") or ""))
    if source == "profile":
        default_cover = defaults.get("cover")
        return Path(default_cover) if default_cover is not None else None
    return normalize_optional_path(str(st.session_state.get("video_input_cover_path") or ""))


def _resolve_scenes_dir(settings: dict[str, Any]) -> Optional[Path]:
    source = str(st.session_state.get("video_scenes_source") or "handoff").strip().lower()
    defaults = settings["defaults"]
    if source == "handoff":
        return normalize_optional_path(workspace_handoff_state(st.session_state).image_scenes_dir or str(st.session_state.get("video_scenes_input") or ""))
    if source == "profile":
        default_scenes = defaults.get("scenes_dir")
        return Path(default_scenes) if default_scenes is not None else None
    return normalize_optional_path(str(st.session_state.get("video_input_scenes_dir") or ""))


def _prepare_video_inputs(settings: dict[str, Any]) -> None:
    _apply_audio_handoff_prefill(settings)
    _apply_image_handoff_prefill(settings)
    _ensure_video_input_defaults(settings)


def _collect_inputs(settings: dict[str, Any]) -> dict[str, Any]:
    _prepare_video_inputs(settings)

    audio_raw = str(st.session_state.get("video_audio_input") or "").strip()
    output_raw = str(st.session_state.get("video_output_input") or "").strip()

    audio_path = Path(audio_raw) if audio_raw else None
    output_path = Path(output_raw) if output_raw else None

    subtitle_path = normalize_optional_path(st.session_state.get("video_subtitle_input") or "")
    if subtitle_path is None and audio_path is not None:
        subtitle_path = autodetect_subtitle_from_audio(audio_path)
    cover_path = _resolve_cover_path(settings)
    scenes_dir = _resolve_scenes_dir(settings)

    errors = validate_inputs(
        audio=audio_path,
        output=output_path,
        mode=str(settings["mode"]),
        cover=cover_path,
        scenes_dir=scenes_dir,
        subtitle=subtitle_path,
    )

    errors.extend(
        validate_runtime_settings(
            ffmpeg_exe=str(settings["ffmpeg_exe"]),
            ffprobe_exe=str(settings["ffprobe_exe"]),
        )
    )
    summary = build_video_run_summary(
        audio=audio_path,
        output=output_path,
        subtitle=subtitle_path,
        cover=cover_path,
        scenes_dir=scenes_dir,
        settings=settings,
    )
    summary["cover_source"] = str(st.session_state.get("video_cover_source") or "handoff")
    summary["scenes_source"] = str(st.session_state.get("video_scenes_source") or "handoff")
    return {
        "audio": audio_path,
        "output": output_path,
        "cover": cover_path,
        "scenes_dir": scenes_dir,
        "subtitle": subtitle_path,
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
            "asset_profile": summary.get("asset_profile"),
        },
        limit=12,
    )



def render_doctor_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    st.subheader("Video doctor")
    _prepare_video_inputs(settings)
    diagnostics = collect_runtime_diagnostics(
        ffmpeg_exe=str(settings.get("ffmpeg_exe") or ""),
        ffprobe_exe=str(settings.get("ffprobe_exe") or ""),
    )
    cover_path = _resolve_cover_path(settings)
    scenes_dir = _resolve_scenes_dir(settings)
    audio_path = normalize_optional_path(str(st.session_state.get("video_audio_input") or ""))
    subtitle_path = normalize_optional_path(str(st.session_state.get("video_subtitle_input") or ""))

    c1, c2, c3 = st.columns(3)
    c1.metric("Mode", str(settings.get("mode") or "-"))
    c2.metric("Asset profile", str(settings.get("asset_profile") or "-"))
    c3.metric("Runtime tools", len(getattr(diagnostics, "tools", []) or []))

    rows = [
        {"check": "Audio input", "status": "OK" if audio_path and audio_path.is_file() else "missing", "detail": str(audio_path or "Audio input not set")},
        {"check": "Subtitle", "status": "OK" if subtitle_path and subtitle_path.is_file() else ("not set" if subtitle_path is None else "missing"), "detail": str(subtitle_path or "Leave empty for autodetect or optional subtitle")},
        {"check": "Cover", "status": "OK" if cover_path and cover_path.is_file() else "missing", "detail": str(cover_path or "Cover not set")},
        {"check": "Scenes dir", "status": "OK" if scenes_dir and scenes_dir.is_dir() else "missing", "detail": str(scenes_dir or "Scenes directory not set")},
        {"check": "Story bundle", "status": "OK" if str(workspace_handoff_state(st.session_state).story_video_handoff_dir or "").strip() else "missing", "detail": str(workspace_handoff_state(st.session_state).story_video_handoff_dir or "Story bundle not set")},
    ]
    st.dataframe(rows, width="stretch", height=240)
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
        "story_bundle": "Story bundle",
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
    defaults = settings["defaults"]

    st.subheader("Inputs")
    _render_video_focus_hint("Inputs")
    st.checkbox(
        "Lock input to Audio handoff",
        key="video_lock_to_audio_handoff",
        help="When enabled, Video keeps following the newest audio/subtitle/output hints sent from Audio handoff.",
    )
    st.checkbox(
        "Lock input to Image handoff",
        key="video_lock_to_image_handoff",
        help="When enabled, Video keeps following the newest cover/scenes hints sent from Image or Story handoff.",
    )
    col_left, col_right = st.columns([1.15, 1.0])
    with col_left:
        st.text_input("Audio file", key="video_audio_input")
        st.text_input(
            "Subtitle file (leave empty = autodetect from audio)",
            key="video_subtitle_input",
        )
        st.text_input("Output MP4", key="video_output_input")
    with col_right:
        st.caption("Asset-driven inputs")
        st.radio(
            "Cover image source",
            options=["handoff", "profile", "input"],
            key="video_cover_source",
            horizontal=True,
        )
        if st.session_state.get("video_cover_source") == "input":
            st.text_input("Input cover image", key="video_input_cover_path")
        elif st.session_state.get("video_cover_source") == "profile":
            st.caption(f"Profile cover: {defaults.get('cover') or '-'}")
        else:
            st.caption(f"Handoff cover: {workspace_handoff_state(st.session_state).image_cover_path or st.session_state.get('video_cover_input') or '-'}")

        st.radio(
            "Scenes directory source",
            options=["handoff", "profile", "input"],
            key="video_scenes_source",
            horizontal=True,
        )
        if st.session_state.get("video_scenes_source") == "input":
            st.text_input("Input scenes directory", key="video_input_scenes_dir")
        elif st.session_state.get("video_scenes_source") == "profile":
            st.caption(f"Profile scenes dir: {defaults.get('scenes_dir') or '-'}")
        else:
            st.caption(f"Handoff scenes dir: {workspace_handoff_state(st.session_state).image_scenes_dir or st.session_state.get('video_scenes_input') or '-'}")

        image_manifest = workspace_handoff_state(st.session_state).image_manifest_path
        if image_manifest:
            st.caption(f"Image manifest: {image_manifest}")
        story_bundle = workspace_handoff_state(st.session_state).story_video_handoff_dir
        if story_bundle:
            st.caption(f"Story bundle: {story_bundle}")
            bundle_cols = st.columns([1.0, 1.0])
            if bundle_cols[0].button("Use Story bundle", key="video_use_story_bundle", width="stretch"):
                try:
                    changes = _import_story_bundle_into_video(Path(str(story_bundle)), settings)
                    st.success(f"Loaded Story bundle into Video. cover={changes['cover']} - scenes={changes['scenes_dir']}")
                except Exception as exc:
                    show_provider_error(
                        "Story bundle",
                        problem="Could not import the current Story bundle into Video inputs.",
                        technical_details=str(exc),
                        show_details=True,
                        actions=[
                            "Check whether bundle_dir contains manifest.json, cover.png, and scene_images/.",
                            "Render Image first if scene_images still does not exist.",
                        ],
                    )
            manifest_path = Path(str(story_bundle)) / "manifest.json"
            missing_items: list[str] = []
            if not manifest_path.is_file():
                missing_items.append("manifest.json")
            if not (Path(str(story_bundle)) / "cover.png").is_file():
                missing_items.append("cover.png")
            if not (Path(str(story_bundle)) / "scene_images").is_dir():
                missing_items.append("scene_images/")
            if missing_items:
                bundle_cols[1].warning("Bundle does not yet contain enough assets to render immediately: " + ", ".join(missing_items))
            else:
                bundle_cols[1].success("Bundle already has cover + scene_images for slideshow/static render.")

    render_json_summary_expander("Run configuration summary", _collect_inputs(settings)["summary"], expanded=False)


def render_run_tab(settings: dict[str, Any]) -> None:
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
                    cover=inputs["cover"],
                    scenes_dir=inputs["scenes_dir"],
                    ffmpeg_exe=settings["ffmpeg_exe"],
                    ffprobe_exe=settings["ffprobe_exe"],
                    video_codec=settings.get("video_codec"),
                    audio_codec=settings.get("audio_codec"),
                    audio_bitrate=settings.get("audio_bitrate"),
                    video_preset=settings.get("video_preset"),
                    video_crf=settings.get("video_crf"),
                    video_fps=settings.get("video_fps"),
                    video_tune=settings.get("video_tune"),
                    video_movflags=settings.get("video_movflags"),
                    slideshow_match_audio=settings.get("slideshow_match_audio"),
                    audio_match_epsilon=settings.get("audio_match_epsilon"),
                    keep_concat_list=settings.get("keep_concat_list"),
                    subtitle_font_size=settings.get("subtitle_font_size"),
                    subtitle_outline=settings.get("subtitle_outline"),
                    subtitle_shadow=settings.get("subtitle_shadow"),
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



def render_test_tab(settings: dict[str, Any]) -> None:
    st.subheader("Test")
    inputs = _collect_inputs(settings)
    summary = dict(inputs.get("summary") or {})

    if inputs.get("errors"):
        for err in inputs["errors"]:
            show_missing_input("video input", hint=err, actions=["Check the selected source again in the Inputs tab."])
    else:
        st.success("Current video inputs resolve successfully.")

    col1, col2 = st.columns(2)
    with col1:
        st.write({
            "audio": str(inputs.get("audio") or ""),
            "subtitle": str(inputs.get("subtitle") or ""),
            "output": str(inputs.get("output") or ""),
        })
    with col2:
        st.write({
            "cover": str(inputs.get("cover") or ""),
            "cover_source": summary.get("cover_source"),
            "scenes_dir": str(inputs.get("scenes_dir") or ""),
            "scenes_source": summary.get("scenes_source"),
        })

    audio_path = inputs.get("audio")
    if audio_path and Path(audio_path).is_file():
        st.audio(str(audio_path))

    cover_path = inputs.get("cover")
    if cover_path and Path(cover_path).is_file():
        st.image(str(cover_path), caption=Path(cover_path).name, width='stretch')

    scenes_dir = inputs.get("scenes_dir")
    if scenes_dir and Path(scenes_dir).is_dir():
        image_files = sorted([p for p in Path(scenes_dir).iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])
        st.caption(f"Available scenes: {len(image_files)} file(s)")
        for image_path in image_files[:12]:
            st.image(str(image_path), caption=image_path.name, width='stretch')

    render_json_summary_expander("Test input summary", summary, expanded=False)

def render_preview_logs_tab(settings: dict[str, Any]) -> None:
    del settings
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
    items = st.session_state.get("video_run_history", [])
    render_session_history(
        items,
        empty_message="No render history is available in the current session.",
        title_builder=lambda idx, item: f"#{idx} | {item.get('output_name') or item.get('output') or 'video'}",
    )
