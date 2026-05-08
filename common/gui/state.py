from __future__ import annotations

import streamlit as st

from common.gui.global_run_monitor import (
    WORKSPACE_JOB_TIMELINE_KEY,
    WORKSPACE_LAST_JOB_APP_KEY,
    WORKSPACE_LAST_JOB_ERROR_KEY,
    WORKSPACE_LAST_JOB_OUTPUT_KEY,
    WORKSPACE_LAST_JOB_PROGRESS_KEY,
    WORKSPACE_LAST_JOB_STAGE_KEY,
    WORKSPACE_LAST_JOB_STATUS_KEY,
    WORKSPACE_LAST_JOB_SUMMARY_KEY,
    global_run_monitor_state,
)
from common.gui.workspace_navigation import (
    WORKSPACE_ACTIVE_APP_KEY,
    WORKSPACE_ACTIVE_APP_SELECTOR_KEY,
    WORKSPACE_AUDIO_TARGET_VIEW_KEY,
    WORKSPACE_IMAGE_TARGET_VIEW_KEY,
    WORKSPACE_PENDING_APP_KEY,
    WORKSPACE_PENDING_VIEW_KEY,
    WORKSPACE_PENDING_FIELD_KEY,
    WORKSPACE_STORY_TARGET_VIEW_KEY,
    WORKSPACE_VIDEO_TARGET_VIEW_KEY,
    WORKSPACE_STORY_TARGET_FIELD_KEY,
    WORKSPACE_AUDIO_TARGET_FIELD_KEY,
    WORKSPACE_IMAGE_TARGET_FIELD_KEY,
    WORKSPACE_VIDEO_TARGET_FIELD_KEY,
    TARGET_VIEW_KEY_MAP,
    workspace_navigation_state,
)
from common.gui.lock_flags import (
    AUDIO_LOCK_TO_STORY_HANDOFF_KEY,
    IMAGE_LOCK_TO_STORY_HANDOFF_KEY,
    VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY,
    VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY,
    LOCK_FLAG_DEFAULTS,
    workspace_lock_flags,
)
from common.gui.pipeline_status import compute_pipeline_status
from common.gui.workspace_source_outputs import (
    WORKSPACE_SOURCE_OUTPUT_DEFAULTS,
    workspace_source_outputs,
)
from common.gui.workspace_handoff import (
    WORKSPACE_AUDIO_OUTPUT_PATH_KEY,
    WORKSPACE_AUDIO_SRT_PATH_KEY,
    WORKSPACE_IMAGE_COVER_PATH_KEY,
    WORKSPACE_IMAGE_MANIFEST_PATH_KEY,
    WORKSPACE_IMAGE_SCENES_DIR_KEY,
    WORKSPACE_LAST_AUDIO_OUTPUT_KEY,
    WORKSPACE_LAST_IMAGE_OUTPUT_KEY,
    WORKSPACE_LAST_STORY_OUTPUT_KEY,
    WORKSPACE_LAST_VIDEO_OUTPUT_KEY,
    WORKSPACE_STORY_IMAGE_HANDOFF_DIR_KEY,
    WORKSPACE_STORY_PLAIN_SCRIPT_TEXT_KEY,
    WORKSPACE_STORY_VIDEO_HANDOFF_DIR_KEY,
    workspace_handoff_state,
)

WORKSPACE_DEFAULTS = {
    WORKSPACE_ACTIVE_APP_KEY: "Overview",
    WORKSPACE_ACTIVE_APP_SELECTOR_KEY: "Overview",
    WORKSPACE_PENDING_APP_KEY: "",
    WORKSPACE_PENDING_VIEW_KEY: "",
    WORKSPACE_PENDING_FIELD_KEY: "",
    WORKSPACE_LAST_STORY_OUTPUT_KEY: "",
    WORKSPACE_LAST_AUDIO_OUTPUT_KEY: "",
    WORKSPACE_LAST_IMAGE_OUTPUT_KEY: "",
    WORKSPACE_LAST_VIDEO_OUTPUT_KEY: "",
    WORKSPACE_STORY_PLAIN_SCRIPT_TEXT_KEY: "",
    WORKSPACE_STORY_IMAGE_HANDOFF_DIR_KEY: "",
    WORKSPACE_STORY_VIDEO_HANDOFF_DIR_KEY: "",
    WORKSPACE_AUDIO_OUTPUT_PATH_KEY: "",
    WORKSPACE_AUDIO_SRT_PATH_KEY: "",
    WORKSPACE_IMAGE_COVER_PATH_KEY: "",
    WORKSPACE_IMAGE_SCENES_DIR_KEY: "",
    WORKSPACE_IMAGE_MANIFEST_PATH_KEY: "",
    AUDIO_LOCK_TO_STORY_HANDOFF_KEY: LOCK_FLAG_DEFAULTS[AUDIO_LOCK_TO_STORY_HANDOFF_KEY],
    IMAGE_LOCK_TO_STORY_HANDOFF_KEY: LOCK_FLAG_DEFAULTS[IMAGE_LOCK_TO_STORY_HANDOFF_KEY],
    VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY: LOCK_FLAG_DEFAULTS[VIDEO_LOCK_TO_AUDIO_HANDOFF_KEY],
    VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY: LOCK_FLAG_DEFAULTS[VIDEO_LOCK_TO_IMAGE_HANDOFF_KEY],
    WORKSPACE_STORY_TARGET_VIEW_KEY: "Inputs",
    WORKSPACE_AUDIO_TARGET_VIEW_KEY: "Input",
    WORKSPACE_IMAGE_TARGET_VIEW_KEY: "Inputs",
    WORKSPACE_VIDEO_TARGET_VIEW_KEY: "Inputs",
    WORKSPACE_STORY_TARGET_FIELD_KEY: "",
    WORKSPACE_AUDIO_TARGET_FIELD_KEY: "",
    WORKSPACE_IMAGE_TARGET_FIELD_KEY: "",
    WORKSPACE_VIDEO_TARGET_FIELD_KEY: "",
    WORKSPACE_LAST_JOB_APP_KEY: "",
    WORKSPACE_LAST_JOB_STAGE_KEY: "",
    WORKSPACE_LAST_JOB_STATUS_KEY: "idle",
    WORKSPACE_LAST_JOB_PROGRESS_KEY: 0,
    WORKSPACE_LAST_JOB_OUTPUT_KEY: "",
    WORKSPACE_LAST_JOB_ERROR_KEY: "",
    WORKSPACE_LAST_JOB_SUMMARY_KEY: None,
    WORKSPACE_JOB_TIMELINE_KEY: [],
    **WORKSPACE_SOURCE_OUTPUT_DEFAULTS,
}

LEGACY_SESSION_KEY_MAP = {
    "studio_active_app": "workspace_active_app",
    "studio_active_app_selector": "workspace_active_app_selector",
    "studio_pending_app": "workspace_pending_app",
    "studio_pending_view": "workspace_pending_view",
    "studio_pending_field": "workspace_pending_field",
    "studio_last_story_output": "workspace_last_story_output",
    "studio_last_audio_output": "workspace_last_audio_output",
    "studio_last_image_output": "workspace_last_image_output",
    "studio_last_video_output": "workspace_last_video_output",
    "studio_story_plain_script_text": "workspace_story_plain_script_text",
    "studio_story_image_handoff_dir": "workspace_story_image_handoff_dir",
    "studio_story_video_handoff_dir": "workspace_story_video_handoff_dir",
    "studio_audio_output_path": "workspace_audio_output_path",
    "studio_audio_srt_path": "workspace_audio_srt_path",
    "studio_image_cover_path": "workspace_image_cover_path",
    "studio_image_scenes_dir": "workspace_image_scenes_dir",
    "studio_image_manifest_path": "workspace_image_manifest_path",
    "studio_story_target_view": "workspace_story_target_view",
    "studio_audio_target_view": "workspace_audio_target_view",
    "studio_image_target_view": "workspace_image_target_view",
    "studio_video_target_view": "workspace_video_target_view",
    "studio_story_target_field": "workspace_story_target_field",
    "studio_audio_target_field": "workspace_audio_target_field",
    "studio_image_target_field": "workspace_image_target_field",
    "studio_video_target_field": "workspace_video_target_field",
    "studio_last_job_app": "workspace_last_job_app",
    "studio_last_job_stage": "workspace_last_job_stage",
    "studio_last_job_status": "workspace_last_job_status",
    "studio_last_job_progress": "workspace_last_job_progress",
    "studio_last_job_output": "workspace_last_job_output",
    "studio_last_job_error": "workspace_last_job_error",
    "studio_last_job_summary": "workspace_last_job_summary",
    "studio_job_timeline": "workspace_job_timeline",
    "_studio_now_override": "_workspace_now_override",
}


def migrate_legacy_session_state() -> None:
    session = st.session_state
    for legacy_key, new_key in LEGACY_SESSION_KEY_MAP.items():
        if legacy_key in session and new_key not in session:
            session[new_key] = session[legacy_key]
    for legacy_key, new_key in LEGACY_SESSION_KEY_MAP.items():
        if new_key in session:
            session[legacy_key] = session[new_key]


def ensure_workspace_shell_state() -> None:
    migrate_legacy_session_state()
    for key, value in WORKSPACE_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    migrate_legacy_session_state()


def ensure_studio_shell_state() -> None:
    ensure_workspace_shell_state()


def request_workspace_navigation(app_name: str, target_view: str | None = None, target_field: str | None = None) -> None:
    ensure_workspace_shell_state()
    navigation = workspace_navigation_state(st.session_state)
    navigation.pending_app = app_name
    navigation.pending_view = target_view or ""
    navigation.pending_field = target_field or ""
    migrate_legacy_session_state()


def request_studio_navigation(app_name: str, target_view: str | None = None, target_field: str | None = None) -> None:
    request_workspace_navigation(app_name, target_view, target_field)


def get_workspace_target_view(app_name: str, default: str = "Run") -> str:
    ensure_workspace_shell_state()
    return workspace_navigation_state(st.session_state).get_target_view(app_name, default)


def get_studio_target_view(app_name: str, default: str = "Run") -> str:
    return get_workspace_target_view(app_name, default)


def set_workspace_target_view(app_name: str, value: str) -> None:
    ensure_workspace_shell_state()
    navigation = workspace_navigation_state(st.session_state)
    navigation.set_target_view(app_name, value)
    migrate_legacy_session_state()


def set_studio_target_view(app_name: str, value: str) -> None:
    set_workspace_target_view(app_name, value)


def get_workspace_target_field(app_name: str, default: str = "") -> str:
    ensure_workspace_shell_state()
    return workspace_navigation_state(st.session_state).get_target_field(app_name, default)


def set_workspace_target_field(app_name: str, value: str) -> None:
    ensure_workspace_shell_state()
    navigation = workspace_navigation_state(st.session_state)
    navigation.set_target_field(app_name, value)
    migrate_legacy_session_state()


def consume_workspace_target_field(app_name: str) -> str:
    ensure_workspace_shell_state()
    navigation = workspace_navigation_state(st.session_state)
    value = navigation.get_target_field(app_name, "")
    navigation.set_target_field(app_name, "")
    migrate_legacy_session_state()
    return value


def get_studio_target_field(app_name: str, default: str = "") -> str:
    return get_workspace_target_field(app_name, default)


def set_studio_target_field(app_name: str, value: str) -> None:
    set_workspace_target_field(app_name, value)

def prepare_embedded_view_selection(*, app_name: str, widget_key: str, options: list[str], default: str) -> str:
    ensure_workspace_shell_state()
    target = get_workspace_target_view(app_name, default=default)
    if target not in options:
        target = default
    current_widget_value = st.session_state.get(widget_key)
    if current_widget_value not in options:
        st.session_state[widget_key] = target
    return target


def sync_embedded_view_selection(*, app_name: str, widget_value: str) -> None:
    ensure_workspace_shell_state()
    set_workspace_target_view(app_name, widget_value)


def set_story_handoff(*, plain_script_text: str, display_value: str = "Plain script ready to send to Audio") -> None:
    ensure_workspace_shell_state()
    handoff = workspace_handoff_state(st.session_state)
    handoff.story_plain_script_text = plain_script_text or ""
    handoff.last_story_output = display_value if plain_script_text else ""
    migrate_legacy_session_state()


def send_story_to_audio(*, plain_script_text: str) -> None:
    set_story_handoff(plain_script_text=plain_script_text)
    workspace_lock_flags(st.session_state).audio_to_story = True
    workspace_navigation_state(st.session_state).set_target_view("Audio", "Run")
    request_workspace_navigation("Audio", "Run")


def set_story_image_handoff(*, handoff_dir: str) -> None:
    ensure_workspace_shell_state()
    handoff = workspace_handoff_state(st.session_state)
    handoff.story_image_handoff_dir = handoff_dir or ""
    if handoff_dir:
        handoff.last_story_output = handoff_dir
    migrate_legacy_session_state()


def send_story_to_image(*, handoff_dir: str) -> None:
    set_story_image_handoff(handoff_dir=handoff_dir)
    workspace_lock_flags(st.session_state).image_to_story = True
    workspace_navigation_state(st.session_state).set_target_view("Image", "Inputs")
    request_workspace_navigation("Image", "Inputs")


def set_story_video_handoff(*, handoff_dir: str) -> None:
    ensure_workspace_shell_state()
    workspace_handoff_state(st.session_state).story_video_handoff_dir = handoff_dir or ""
    migrate_legacy_session_state()


def set_audio_handoff(*, audio_output_path: str, srt_output_path: str = "") -> None:
    ensure_workspace_shell_state()
    handoff = workspace_handoff_state(st.session_state)
    handoff.audio_output_path = audio_output_path or ""
    handoff.audio_srt_path = srt_output_path or ""
    handoff.last_audio_output = audio_output_path or ""
    migrate_legacy_session_state()


def send_audio_to_video(*, audio_output_path: str, srt_output_path: str = "") -> None:
    set_audio_handoff(audio_output_path=audio_output_path, srt_output_path=srt_output_path)
    workspace_lock_flags(st.session_state).video_to_audio = True
    workspace_navigation_state(st.session_state).set_target_view("Video", "Inputs")
    request_workspace_navigation("Video", "Inputs")


def set_image_handoff(*, cover_image_path: str, scene_images_dir: str, manifest_path: str = "") -> None:
    ensure_workspace_shell_state()
    handoff = workspace_handoff_state(st.session_state)
    handoff.image_cover_path = cover_image_path or ""
    handoff.image_scenes_dir = scene_images_dir or ""
    handoff.image_manifest_path = manifest_path or ""
    handoff.last_image_output = scene_images_dir or cover_image_path or ""
    migrate_legacy_session_state()


def send_image_to_video(*, cover_image_path: str, scene_images_dir: str, manifest_path: str = "") -> None:
    set_image_handoff(cover_image_path=cover_image_path, scene_images_dir=scene_images_dir, manifest_path=manifest_path)
    workspace_lock_flags(st.session_state).video_to_image = True
    workspace_navigation_state(st.session_state).set_target_view("Video", "Inputs")
    request_workspace_navigation("Video", "Inputs")


def set_video_handoff(*, video_output_path: str) -> None:
    ensure_workspace_shell_state()
    workspace_handoff_state(st.session_state).last_video_output = video_output_path or ""
    migrate_legacy_session_state()


def sync_pipeline_handoff_state() -> None:
    ensure_workspace_shell_state()
    handoff = workspace_handoff_state(st.session_state)
    outputs = workspace_source_outputs(st.session_state)
    if outputs.story_plain_script_path:
        handoff.last_story_output = outputs.story_plain_script_path
    if outputs.audio_output:
        handoff.last_audio_output = outputs.audio_output
        handoff.audio_output_path = outputs.audio_output
    if outputs.audio_srt_output:
        handoff.audio_srt_path = outputs.audio_srt_output
    if outputs.image_cover_output or outputs.image_scenes_dir:
        handoff.image_cover_path = outputs.image_cover_output
        handoff.image_scenes_dir = outputs.image_scenes_dir
        handoff.last_image_output = outputs.image_scenes_dir or outputs.image_cover_output
    if outputs.video_output:
        handoff.last_video_output = outputs.video_output
    migrate_legacy_session_state()


def get_pipeline_status_snapshot() -> dict[str, str]:
    ensure_workspace_shell_state()
    return compute_pipeline_status(st.session_state).as_dict()


def ensure_global_run_monitor_state() -> None:
    ensure_workspace_shell_state()
    for key, value in {
        WORKSPACE_LAST_JOB_APP_KEY: "",
        WORKSPACE_LAST_JOB_STAGE_KEY: "",
        WORKSPACE_LAST_JOB_STATUS_KEY: "idle",
        WORKSPACE_LAST_JOB_PROGRESS_KEY: 0,
        WORKSPACE_LAST_JOB_OUTPUT_KEY: "",
        WORKSPACE_LAST_JOB_ERROR_KEY: "",
        WORKSPACE_LAST_JOB_SUMMARY_KEY: None,
        WORKSPACE_JOB_TIMELINE_KEY: [],
    }.items():
        st.session_state.setdefault(key, value)
    for key, value in LOCK_FLAG_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    migrate_legacy_session_state()


def update_global_run_monitor(*, app: str, stage: str, status: str, progress: int | float = 0, output_path: str = "", error_text: str = "", summary: dict | None = None) -> None:
    ensure_global_run_monitor_state()
    monitor = global_run_monitor_state(st.session_state)
    monitor.app = app
    monitor.stage = stage
    monitor.status = status
    monitor.progress = progress
    monitor.output = output_path or ""
    monitor.error = error_text or ""
    monitor.summary = summary
    migrate_legacy_session_state()


def get_global_run_monitor_snapshot() -> dict[str, object]:
    ensure_global_run_monitor_state()
    return global_run_monitor_state(st.session_state).snapshot()


def append_global_run_event(*, app: str, stage: str, status: str, message: str = "", output_path: str = "", error_text: str = "") -> None:
    ensure_global_run_monitor_state()
    global_run_monitor_state(st.session_state).append_timeline_event(
        app=app,
        stage=stage,
        status=status,
        message=message,
        output_path=output_path,
        error_text=error_text,
    )
    migrate_legacy_session_state()


def get_global_run_timeline() -> list[dict[str, str]]:
    ensure_global_run_monitor_state()
    return global_run_monitor_state(st.session_state).timeline


def clear_global_run_timeline() -> None:
    ensure_global_run_monitor_state()
    global_run_monitor_state(st.session_state).timeline = []
    migrate_legacy_session_state()
