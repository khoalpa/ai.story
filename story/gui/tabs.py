from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, MutableMapping

import streamlit as st
import yaml

from story.gui.input_bundle import load_input_story, scan_input_bundle
from story.testing import llm_config_fingerprint, run_llm_smoke_test
from story.audio_story_spec import render_plain_script, validate_canonical_authoring
from story.convert_raw_to_script import SpeakerConfig, convert_text
from story.validate_canonical_authoring import extract_auto_repair_log, validate_script_length_rule
from story.validate_plain_script import validate_script
from story.handoff import write_handoff

from story.gui.handoff_utils import HandoffAction, render_handoff_action_row
from story.gui.diagnostics_blocks import render_runtime_diagnostics_block
from story.gui.panel_utils import render_json_summary_expander, render_session_history
from story.gui.result_panels import DownloadSpec, MetricSpec, render_download_button_row, render_metrics_row
from story.gui.user_messages import UserMessage, render_user_message, show_missing_input, show_provider_error
from story.gui.workspace_state import (
    append_global_run_event,
    get_workspace_target_field,
    send_story_to_audio,
    send_story_to_image,
    send_image_to_video,
    set_story_handoff,
    set_story_image_handoff,
    set_story_video_handoff,
    update_global_run_monitor,
)
from story.gui.runtime_usage import render_runtime_usage_compact
from story.gui.progress_details import format_duration, format_progress_text
from story.gui.workspace_handoff import workspace_handoff_state
from story.gui.workspace_source_outputs import workspace_source_outputs
from story.gui.briefs import (
    list_brief_yaml_files,
    load_brief_text,
    make_brief_option_labels,
    recommended_brief_label_for_mode,
    selected_brief_path,
)
from story.gui.errors import build_error_context, format_runtime_error, split_runtime_error_details, summarize_settings_for_logs
from story.gui.history import append_draft_history, append_history, append_outline_history, estimate_draft_seconds, estimate_outline_seconds
from story.gui.image_prompts import dumps_json
from story.gui.output_paths import resolve_story_output_base, save_story_step_json
from story.gui.diagnostics import collect_runtime_diagnostics
from story.gui.llm_test import _build_test_cfg, current_llm_status, current_test_prompts, render_llm_test_panel
from story.gui.prompts import (
    list_system_prompt_files,
    load_system_prompt_text,
    make_system_prompt_option_labels,
    recommended_system_prompt_label_for_mode,
    selected_system_prompt_path,
)
from story.gui.service import generate_story, generate_story_draft, generate_story_outline, validate_and_render_story_result
from story.gui.split_jobs import attach_image_prompts_and_handoff, build_story_output_bundle, image_prompt_handoff_ready
from story.gui.view_models import build_story_run_summary

ResultDict = dict[str, Any]


def reset_story_outputs_after_outline(state: MutableMapping[str, Any]) -> None:
    state["story_authoring_draft"] = None
    state["story_last_result"] = None
    state["story_last_failed_result"] = None
    state["story_last_error_context"] = None
    workspace_source_outputs(state).story_plain_script_path = ""
    handoff = workspace_handoff_state(state)
    handoff.story_plain_script_text = ""
    handoff.last_story_output = ""
    clear_story_visual_handoffs(state)


def clear_story_visual_handoffs(state: MutableMapping[str, Any]) -> None:
    handoff = workspace_handoff_state(state)
    handoff.story_image_handoff_dir = ""
    handoff.story_video_handoff_dir = ""


def append_generate_all_phase_history(
    *,
    phase_elapsed_s: dict[str, float],
    target_duration_min: int | None,
    settings: dict[str, Any],
    result: dict[str, Any],
    state: MutableMapping[str, Any],
) -> None:
    outline_elapsed = phase_elapsed_s.get("outline")
    if outline_elapsed is not None:
        append_outline_history(
            elapsed_s=outline_elapsed,
            target_duration_min=target_duration_min,
            mode=str(result.get("mode") or settings.get("mode") or ""),
            max_tokens=int((result.get("settings_summary") or {}).get("outline_max_tokens") or settings.get("max_tokens") or 0),
            state=state,
        )
    draft_elapsed = phase_elapsed_s.get("generate")
    if draft_elapsed is not None:
        append_draft_history(
            elapsed_s=draft_elapsed,
            target_duration_min=target_duration_min,
            mode=str(result.get("mode") or settings.get("mode") or ""),
            max_tokens=int((result.get("settings_summary") or {}).get("max_tokens") or settings.get("max_tokens") or 0),
            chunked=bool((result.get("settings_summary") or {}).get("chunked", settings.get("chunked"))),
            chunk_size=int((result.get("settings_summary") or {}).get("chunk_size") or settings.get("chunk_size") or 0),
            state=state,
        )


def target_duration_min_from_brief(brief: dict[str, Any]) -> int | None:
    goals = brief.get("goals") if isinstance(brief, dict) else {}
    if not isinstance(goals, dict):
        return None
    try:
        value = int(goals.get("target_duration_min") or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def outline_estimate_details(*, target_duration_min: int | None, history: list[dict[str, Any]]) -> list[str]:
    details: list[str] = []
    if target_duration_min:
        details.append(f"target_duration={target_duration_min}m")
    estimated_s, sample_count = estimate_outline_seconds(target_duration_min, history)
    if estimated_s is None:
        details.append("estimate=learning history")
    else:
        details.append(f"estimate={format_duration(estimated_s)}")
        details.append(f"history_samples={sample_count}")
    return details


def draft_estimate_details(*, target_duration_min: int | None, history: list[dict[str, Any]]) -> list[str]:
    details: list[str] = []
    if target_duration_min:
        details.append(f"target_duration={target_duration_min}m")
    estimated_s, sample_count = estimate_draft_seconds(target_duration_min, history)
    if estimated_s is None:
        details.append("draft_estimate=learning history")
    else:
        details.append(f"draft_estimate={format_duration(estimated_s)}")
        details.append(f"draft_history_samples={sample_count}")
    return details


def _render_story_focus_hint(view_name: str) -> None:
    if st.session_state.get("workspace_active_app") != "Story":
        return
    if st.session_state.get("story_embedded_view_selector") != view_name:
        return
    target_field = str(get_workspace_target_field("Story", "") or "").strip()
    if not target_field:
        return
    mapping = {
        "brief_text": "Brief YAML",
        "system_prompt": "System prompt",
        "run": "Story Run",
        "tools": "Story Tools",
        "doctor": "Story Doctor",
        "test_llm": "Story Test LLM",
        "preview": "Story Preview & Logs",
        "story_bundle": "Story bundle",
    }
    st.info(f"Deep-link target: {mapping.get(target_field, target_field)}")


def _sync_recommended_selections(
    settings: dict[str, Any],
    brief_labels: list[str],
    prompt_labels: list[str],
    *,
    brief_paths: list[Path],
    prompt_paths: list[Path],
    project_root: Path | None = None,
) -> None:
    mode = str(settings.get("mode") or "")
    if st.session_state.get("story_mode_last") == mode:
        return

    recommended_brief_label = st.session_state.get("story_recommended_brief_label")
    recommended_prompt_label = st.session_state.get("story_recommended_system_prompt_label")

    if recommended_brief_label in brief_labels:
        st.session_state.story_selected_brief_label = recommended_brief_label
        chosen_brief_path = selected_brief_path(recommended_brief_label, brief_paths, project_root=project_root)
        if chosen_brief_path is not None:
            st.session_state.story_brief_text = load_brief_text(chosen_brief_path)
            st.session_state.story_selected_brief = str(chosen_brief_path)

    if recommended_prompt_label in prompt_labels:
        st.session_state.story_selected_system_prompt_label = recommended_prompt_label
        chosen_prompt_path = selected_system_prompt_path(recommended_prompt_label, prompt_paths, project_root=project_root)
        if chosen_prompt_path is not None:
            st.session_state.story_system_prompt_text = load_system_prompt_text(chosen_prompt_path)
            st.session_state.story_selected_system_prompt = str(chosen_prompt_path)

    st.session_state.story_mode_last = mode


def _render_recommended_pair_notice(
    *,
    brief_label: str,
    prompt_label: str,
    brief_paths: list[Path],
    prompt_paths: list[Path],
    project_root: Path | None,
) -> None:
    chosen_brief_path = selected_brief_path(brief_label, brief_paths, project_root=project_root)
    chosen_prompt_path = selected_system_prompt_path(prompt_label, prompt_paths, project_root=project_root)
    msg_parts = [f"Suggestion for the current mode: Brief = {brief_label}; Prompt = {prompt_label}"]
    if chosen_brief_path is None and chosen_prompt_path is None:
        render_user_message(UserMessage(level="info", title="Story presets", body=msg_parts[0]))
        return
    st.caption(msg_parts[0])
    cols = st.columns(2)
    if chosen_brief_path is not None:
        cols[0].code(str(chosen_brief_path))
    else:
        cols[0].write("No matching sample brief found.")
    if chosen_prompt_path is not None:
        cols[1].code(str(chosen_prompt_path))
    else:
        cols[1].write("No matching sample prompt found.")
    if st.button("Load sample pair for mode", width="stretch"):
        if chosen_brief_path is not None:
            st.session_state.story_brief_text = load_brief_text(chosen_brief_path)
            st.session_state.story_selected_brief = str(chosen_brief_path)
            st.session_state.story_selected_brief_label = brief_label
        if chosen_prompt_path is not None:
            st.session_state.story_system_prompt_text = load_system_prompt_text(chosen_prompt_path)
            st.session_state.story_selected_system_prompt = str(chosen_prompt_path)
            st.session_state.story_selected_system_prompt_label = prompt_label


def render_inputs_tab(settings: dict[str, Any], *, project_root: Path | None = None) -> tuple[str, str]:
    if project_root is None and settings.get("project_root"):
        project_root = Path(str(settings["project_root"]))
    modes_root = Path(str(settings["modes_root"])).expanduser() if settings.get("modes_root") else None
    brief_paths = list_brief_yaml_files(project_root=project_root, modes_root=modes_root)
    brief_labels = make_brief_option_labels(brief_paths, project_root=project_root)
    prompt_paths = list_system_prompt_files(project_root=project_root, modes_root=modes_root)
    prompt_labels = make_system_prompt_option_labels(prompt_paths, project_root=project_root)

    recommended_brief_label = recommended_brief_label_for_mode(
        str(settings.get("mode") or ""),
        brief_paths,
        project_root=project_root,
        modes_root=modes_root,
    )
    recommended_prompt_label = recommended_system_prompt_label_for_mode(
        str(settings.get("mode") or ""),
        prompt_paths,
        project_root=project_root,
        modes_root=modes_root,
    )
    st.session_state.story_recommended_brief_label = recommended_brief_label
    st.session_state.story_recommended_system_prompt_label = recommended_prompt_label
    _sync_recommended_selections(
        settings,
        brief_labels,
        prompt_labels,
        brief_paths=brief_paths,
        prompt_paths=prompt_paths,
        project_root=project_root,
    )
    _render_recommended_pair_notice(
        brief_label=recommended_brief_label,
        prompt_label=recommended_prompt_label,
        brief_paths=brief_paths,
        prompt_paths=prompt_paths,
        project_root=project_root,
    )
    input_bundle = scan_input_bundle("input")
    with st.expander("Input sample", expanded=False):
        st.json(input_bundle.summary())
        if st.button("Load canonical story from input/story.json", key="story_load_input_story", width="stretch", disabled=not input_bundle.has_story):
            try:
                authoring = load_input_story("input")
                errors = validate_canonical_authoring(authoring)
                if errors:
                    raise ValueError("; ".join(errors[:3]))
                plain_script = render_plain_script(authoring)
                st.session_state["story_last_result"] = {
                    "plain_script": plain_script,
                    "authoring": authoring,
                    "canonical_json": authoring,
                    "plain_script_path": "",
                    "canonical_json_path": str(input_bundle.story_path),
                    "source": "input",
                }
                st.session_state["workspace_story_plain_script_text"] = plain_script
                st.session_state["workspace_last_story_output"] = str(input_bundle.story_path)
                st.session_state["run_plain_text"] = plain_script
                st.session_state["last_plain_script"] = plain_script
                st.session_state["audio_last_auto_plain_script"] = plain_script
                st.session_state["audio_lock_to_story_handoff"] = True
                st.success("Loaded input/story.json into Story and Audio.")
            except Exception as exc:
                st.warning(f"Could not load input story: {exc}")
    selected_brief_label = st.selectbox("Choose Brief YAML", brief_labels, key="story_selected_brief_label")
    chosen_brief_path = selected_brief_path(selected_brief_label, brief_paths, project_root=project_root)
    if chosen_brief_path is not None:
        cols = st.columns(2)
        cols[0].code(str(chosen_brief_path))
        if cols[1].button("Load selected Brief", width="stretch"):
            st.session_state.story_brief_text = load_brief_text(chosen_brief_path)
            st.session_state.story_selected_brief = str(chosen_brief_path)

    selected_prompt_label = st.selectbox("Choose System Prompt", prompt_labels, key="story_selected_system_prompt_label")
    chosen_prompt_path = selected_system_prompt_path(selected_prompt_label, prompt_paths, project_root=project_root)
    if chosen_prompt_path is not None:
        cols = st.columns(2)
        cols[0].code(str(chosen_prompt_path))
        if cols[1].button("Load selected Prompt", width="stretch"):
            st.session_state.story_system_prompt_text = load_system_prompt_text(chosen_prompt_path)
            st.session_state.story_selected_system_prompt = str(chosen_prompt_path)

    brief_text = st.text_area("Brief YAML", key="story_brief_text", height=320)
    system_prompt = st.text_area("System prompt", key="story_system_prompt_text", height=260)
    try:
        brief = yaml.safe_load(brief_text) or {}
    except Exception as exc:
        brief = {}
        show_missing_input("valid Brief YAML", hint="Fix the YAML syntax before running.", actions=[f"Error details: {exc}"])
    render_json_summary_expander(
        "Run configuration summary",
        {"settings": summarize_settings_for_logs(settings), "brief_summary": build_story_run_summary(settings, brief)},
        expanded=False,
    )
    return brief_text, system_prompt


def make_progress_sink(
    progress: Any,
    log_slot: Any,
    logs: list[str],
    *,
    mode: str = "",
    outline_details: list[str] | None = None,
    draft_details: list[str] | None = None,
) -> Callable[[str, str], None]:
    started_at = time.monotonic()
    phase_order = ["meta", "outline", "chunk", "generate", "handoff"]
    phase_labels = {
        "meta": "Load config",
        "outline": "Build outline",
        "chunk": "Generate chunks",
        "generate": "Generate story",
        "handoff": "Prepare handoff",
    }

    def sink(phase: str, message: str) -> None:
        logs.append(f"[{phase}] {message}")
        frac_map = {"meta": 0.15, "outline": 0.25, "chunk": 0.6, "generate": 0.6}
        frac = frac_map.get(phase, 0.4)
        phase_index = phase_order.index(phase) + 1 if phase in phase_order else 0
        details = [
            f"phase={phase_labels.get(phase, phase or 'unknown')}",
            f"step={phase_index}/{len(phase_order)}" if phase_index else "",
            f"mode={mode}" if mode else "",
            f"elapsed={format_duration(time.monotonic() - started_at)}",
        ]
        if phase == "outline":
            details.extend(outline_details or [])
        if phase == "generate":
            details.extend(draft_details or [])
        progress.progress(frac, text=format_progress_text(frac * 100, message, details))
        log_slot.code("\n".join(logs[-20:]))
        render_runtime_usage_compact()

    return sink


def render_run_tab(settings: dict[str, Any], *, brief_text: str, system_prompt: str) -> None:
    _render_story_focus_hint("Run")
    progress = st.progress(0.0, text=format_progress_text(0, "Not started", [f"mode={settings.get('mode') or '-'}"]))
    log_slot = st.empty()
    logs: list[str] = []
    try:
        brief_for_estimate = yaml.safe_load(brief_text) or {}
    except Exception:
        brief_for_estimate = {}
    target_duration_min = target_duration_min_from_brief(brief_for_estimate if isinstance(brief_for_estimate, dict) else {})
    outline_details = outline_estimate_details(
        target_duration_min=target_duration_min,
        history=list(st.session_state.get("story_outline_history") or []),
    )
    draft_details = draft_estimate_details(
        target_duration_min=target_duration_min,
        history=list(st.session_state.get("story_draft_history") or []),
    )
    sink = make_progress_sink(progress, log_slot, logs, mode=str(settings.get("mode") or ""), outline_details=outline_details, draft_details=draft_details)
    status = current_llm_status(settings)
    badge = {"ok": "[OK]", "error": "[ERROR]", "stale": "[STALE]", "unknown": "[UNKNOWN]"}.get(status["state"], "[UNKNOWN]")
    st.caption(f"{badge} {status['label']} - {status['detail']}")
    if settings.get("test_before_generate"):
        render_user_message(UserMessage(level="info", title="Story preflight", body="Preflight is enabled: the app will run a short Test LLM before generation."))

    def _save_story_outputs(result: dict[str, Any]) -> tuple[str, str]:
        output_base = resolve_story_output_base(settings.get("output_base"))
        txt_path = output_base.with_suffix(".txt")
        json_path = output_base.with_suffix(".json")
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(str(result.get("plain_script") or ""), encoding="utf-8", newline="\n")
        json_path.write_text(
            json.dumps(result.get("authoring") or {}, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        result["plain_script_path"] = str(txt_path)
        result["canonical_json_path"] = str(json_path)
        manifest_path = write_handoff(
            txt_path.parent / "story_audio_handoff.json",
            kind="story.audio-handoff",
            artifacts={"plain_script": txt_path, "canonical_story": json_path},
        )
        result["audio_handoff_manifest"] = str(manifest_path)
        return str(txt_path), str(json_path)

    def _commit_story_result(result: dict[str, Any]) -> None:
        plain_script_path, canonical_json_path = _save_story_outputs(result)
        st.session_state.story_last_result = result
        st.session_state.story_last_failed_result = None
        st.session_state.story_last_error_context = None
        st.session_state.story_last_error = ""
        clear_story_visual_handoffs(st.session_state)
        workspace_source_outputs(st.session_state).story_plain_script_path = plain_script_path
        set_story_handoff(plain_script_text=result.get("plain_script") or "")
        workspace_handoff_state(st.session_state).last_story_output = plain_script_path
        st.session_state["story_audio_handoff_manifest"] = str(result.get("audio_handoff_manifest") or "")
        st.session_state.story_last_canonical_json_path = canonical_json_path
        append_history(result)

    step_cols = st.columns([1.0, 1.0, 1.0])
    if step_cols[0].button("Generate outline", width="stretch"):
        try:
            outline_started_at = time.monotonic()
            outline = generate_story_outline(brief_text=brief_text, system_prompt=system_prompt, settings=settings, event_sink=sink)
            append_outline_history(
                elapsed_s=time.monotonic() - outline_started_at,
                target_duration_min=target_duration_min,
                mode=str(outline.get("mode") or settings.get("mode") or ""),
                max_tokens=int((outline.get("settings_summary") or {}).get("outline_max_tokens") or settings.get("max_tokens") or 0),
                state=st.session_state,
            )
            st.session_state.story_outline_result = outline
            outline_path = save_story_step_json(outline.get("outline_payload") or {}, output_base=settings.get("output_base"), step="outline")
            outline["outline_path"] = str(outline_path)
            reset_story_outputs_after_outline(st.session_state)
            st.session_state.story_last_error = ""
            st.success("Outline generated successfully")
        except Exception as exc:
            friendly_error = format_runtime_error(exc)
            st.session_state.story_last_error = friendly_error
            st.session_state.story_last_error_context = build_error_context(exc)
            friendly_problem, technical_details = split_runtime_error_details(friendly_error)
            show_provider_error(
                "Story outline",
                problem=friendly_problem,
                actions=[
                    "Check the brief, system prompt, and LLM configuration.",
                    "If the local model still returns empty output, increase Max tokens or rerun Test LLM.",
                ],
                technical_details=technical_details,
                show_details=bool(technical_details),
            )

    if step_cols[1].button("Generate draft", width="stretch", disabled=not bool(st.session_state.get("story_outline_result"))):
        try:
            outline = st.session_state.get("story_outline_result") or {}
            draft_started_at = time.monotonic()
            draft = generate_story_draft(
                brief_text=brief_text,
                system_prompt=system_prompt,
                settings=settings,
                outline_payload=outline.get("outline_payload"),
                event_sink=sink,
            )
            append_draft_history(
                elapsed_s=time.monotonic() - draft_started_at,
                target_duration_min=target_duration_min,
                mode=str(draft.get("mode") or settings.get("mode") or ""),
                max_tokens=int((draft.get("settings_summary") or {}).get("max_tokens") or settings.get("max_tokens") or 0),
                chunked=bool((draft.get("settings_summary") or {}).get("chunked", settings.get("chunked"))),
                chunk_size=int((draft.get("settings_summary") or {}).get("chunk_size") or settings.get("chunk_size") or 0),
                state=st.session_state,
            )
            st.session_state.story_authoring_draft = draft
            draft_path = save_story_step_json(draft.get("authoring") or {}, output_base=settings.get("output_base"), step="draft")
            draft["draft_path"] = str(draft_path)
            st.session_state.story_last_error = ""
            st.success("Draft generated successfully")
        except Exception as exc:
            friendly_error = format_runtime_error(exc)
            st.session_state.story_last_error = friendly_error
            show_provider_error("Story draft", problem=friendly_error, actions=["Check the current outline and rerun Generate draft."])

    if step_cols[2].button("Validate + render", width="stretch", disabled=not bool(st.session_state.get("story_authoring_draft"))):
        try:
            draft = st.session_state.get("story_authoring_draft") or {}
            result = validate_and_render_story_result(draft=draft, settings=settings)
            _commit_story_result(result)
            st.success("Story validated and rendered successfully")
        except Exception as exc:
            friendly_error = format_runtime_error(exc)
            error_context = build_error_context(exc)
            st.session_state.story_last_error = friendly_error
            st.session_state.story_last_error_context = error_context
            show_provider_error("Story validate", problem=friendly_error, actions=["Check the current draft and rerun Validate + render."])

    if st.button("Generate all story steps", type="primary", width="stretch"):
        try:
            if settings.get("test_before_generate"):
                progress.progress(0.05, text=format_progress_text(5, "Testing LLM connection", [f"mode={settings.get('mode') or '-'}"]))
                test_cfg = _build_test_cfg(settings)
                resolved_system_prompt, resolved_user_prompt = current_test_prompts()
                st.session_state.story_llm_test_system_prompt = resolved_system_prompt
                st.session_state.story_llm_test_user_prompt = resolved_user_prompt
                test_result = run_llm_smoke_test(
                    test_cfg,
                    system_prompt=resolved_system_prompt,
                    user_prompt=resolved_user_prompt,
                )
                st.session_state.story_llm_test_result = test_result
                st.session_state.story_llm_test_error = ""
                st.session_state.story_llm_test_cfg_fingerprint = llm_config_fingerprint(test_cfg)
                logs.append(f"[test] LLM ready - latency={test_result.get('latency_ms')} ms")
                log_slot.code("\n".join(logs[-20:]))
            update_global_run_monitor(app="Story", stage="Generate", status="running", progress=10, summary={"mode": settings.get("mode")})
            append_global_run_event(app="Story", stage="Generate", status="running", message=f"mode={settings.get('mode')}")
            phase_started_at: dict[str, float] = {}
            phase_elapsed_s: dict[str, float] = {}

            def timed_sink(phase: str, message: str) -> None:
                now = time.monotonic()
                if phase == "outline" and "outline" not in phase_started_at:
                    phase_started_at["outline"] = now
                if phase == "generate":
                    if "outline" in phase_started_at and "outline" not in phase_elapsed_s:
                        phase_elapsed_s["outline"] = now - phase_started_at["outline"]
                    if "generate" not in phase_started_at:
                        phase_started_at["generate"] = now
                sink(phase, message)

            result = generate_story(brief_text=brief_text, system_prompt=system_prompt, settings=settings, event_sink=timed_sink)
            if "generate" in phase_started_at:
                phase_elapsed_s["generate"] = time.monotonic() - phase_started_at["generate"]
            append_generate_all_phase_history(
                phase_elapsed_s=phase_elapsed_s,
                target_duration_min=target_duration_min,
                settings=settings,
                result=result,
                state=st.session_state,
            )
            plain_script_path, canonical_json_path = _save_story_outputs(result)
            st.session_state.story_last_result = result
            st.session_state.story_last_failed_result = None
            st.session_state.story_last_error_context = None
            st.session_state.story_last_error = ""
            plain_script_text = result.get("plain_script") or ""
            update_global_run_monitor(
                app="Story",
                stage="Generate",
                status="completed",
                progress=100,
                summary={
                    "mode": result.get("mode"),
                    "title": ((result.get("authoring") or {}).get("meta") or {}).get("title"),
                    "script_items": len((result.get("authoring") or {}).get("script") or []),
                },
            )
            append_global_run_event(app="Story", stage="Generate", status="completed", message=f"title={(((result.get('authoring') or {}).get('meta') or {}).get('title') or '-')}")
            clear_story_visual_handoffs(st.session_state)
            workspace_source_outputs(st.session_state).story_plain_script_path = plain_script_path
            st.session_state.story_last_canonical_json_path = canonical_json_path
            set_story_handoff(plain_script_text=plain_script_text)
            workspace_handoff_state(st.session_state).last_story_output = plain_script_path
            st.session_state["story_audio_handoff_manifest"] = str(result.get("audio_handoff_manifest") or "")
            progress.progress(1.0, text=format_progress_text(100, "Complete", [f"mode={result.get('mode') or settings.get('mode') or '-'}"]))
            st.success("Story generated successfully")
            append_history(result)
        except Exception as exc:
            friendly_error = format_runtime_error(exc)
            error_context = build_error_context(exc)
            st.session_state.story_last_result = None
            st.session_state.story_last_error = friendly_error
            st.session_state.story_last_error_context = error_context
            if error_context.get("authoring"):
                st.session_state.story_last_failed_result = {
                    "authoring": error_context.get("authoring"),
                    "plain_script": error_context.get("plain_script") or "",
                }
            else:
                st.session_state.story_last_failed_result = None
            if settings.get("test_before_generate") and not st.session_state.get("story_llm_test_error"):
                st.session_state.story_llm_test_result = None
                st.session_state.story_llm_test_error = friendly_error
                st.session_state.story_llm_test_cfg_fingerprint = llm_config_fingerprint(_build_test_cfg(settings))
            update_global_run_monitor(app="Story", stage="Generate", status="failed", progress=100, error_text=friendly_error, summary={"mode": settings.get("mode")})
            append_global_run_event(app="Story", stage="Generate", status="failed", message="Story generation failed", error_text=friendly_error)
            show_provider_error("Story generation", problem=friendly_error, actions=["Check the brief, system prompt, and LLM configuration again.", "Check the logs or Test LLM to confirm the endpoint is working."])
            if error_context.get("item_index") is not None:
                item_index = error_context.get("item_index")
                render_user_message(UserMessage(level="info", title="Story diagnostics", body=f"Detected the failing item: script[{item_index}]. Open Preview & Logs to inspect the item and highlighted line."))
    can_generate_image_prompts = bool(st.session_state.get("story_last_result"))
    if st.button("Generate image prompts", width="stretch", disabled=not can_generate_image_prompts):
        try:
            result = st.session_state.get("story_last_result") or {}
            update_global_run_monitor(app="Story", stage="Image prompts", status="running", progress=25, summary={"mode": result.get("mode")})
            append_global_run_event(app="Story", stage="Image prompts", status="running", message=f"mode={result.get('mode')}")
            bundle_dir = attach_image_prompts_and_handoff(result)
            st.session_state.story_last_result = result
            set_story_image_handoff(handoff_dir=str(bundle_dir))
            set_story_video_handoff(handoff_dir=str(bundle_dir))
            update_global_run_monitor(
                app="Story",
                stage="Image prompts",
                status="completed",
                progress=100,
                output_path=str(bundle_dir),
                summary={
                    "title": ((result.get("authoring") or {}).get("meta") or {}).get("title"),
                    "image_prompts": len(result.get("image_prompts") or {}),
                },
            )
            append_global_run_event(app="Story", stage="Image prompts", status="completed", message=f"prompts={len(result.get('image_prompts') or {})}", output_path=str(bundle_dir))
            st.success("Image prompts generated successfully")
        except Exception as exc:
            friendly_error = format_runtime_error(exc)
            update_global_run_monitor(app="Story", stage="Image prompts", status="failed", progress=100, error_text=friendly_error)
            append_global_run_event(app="Story", stage="Image prompts", status="failed", message="Image prompt generation failed", error_text=friendly_error)
            show_provider_error("Story image prompts", problem=friendly_error, actions=["Check the current canonical story.", "Rerun Generate image prompts after the story is valid."])
    render_last_result_summary()


def _build_output_bundle(result: dict[str, Any]) -> bytes:
    return build_story_output_bundle(result)


def render_last_result_summary() -> None:
    result = st.session_state.get("story_last_result")
    if not result:
        return
    st.divider()
    st.subheader("Latest result")
    meta = (result.get("authoring") or {}).get("meta") or {}
    mode_title = result.get("mode_label") or result.get("mode") or "-"
    base_mode = result.get("base_mode") or "-"
    render_metrics_row([
        MetricSpec("Mode", mode_title, delta=f"base: {base_mode}"),
        MetricSpec("Script items", len((result.get("authoring") or {}).get("script") or [])),
        MetricSpec("Language", meta.get("language") or "-"),
        MetricSpec("Image prompts", len(result.get("image_prompts") or {})),
    ])

    bundle_bytes = _build_output_bundle(result)
    image_handoff_dir = str(result.get("image_handoff_dir") or "")
    plain_script_path = str(result.get("plain_script_path") or "")
    canonical_json_path = str(result.get("canonical_json_path") or "")
    prompts_ready = image_prompt_handoff_ready(result)
    handoff_actions = [
        HandoffAction(
            label="Send to Audio",
            key="send_story_to_audio_btn",
            callback=lambda: send_story_to_audio(plain_script_text=result.get("plain_script") or ""),
            success_message="Sent the plain script to Audio and enabled the handoff lock.",
        )
    ]
    if prompts_ready:
        handoff_actions.extend([
            HandoffAction(
                label="Send to Image",
                key="send_story_to_image_btn",
                callback=lambda: send_story_to_image(handoff_dir=image_handoff_dir),
                success_message="Sent the prompt bundle to Image.",
            ),
            HandoffAction(
                label="Send to Video",
                key="send_story_to_video_btn",
                callback=lambda: send_image_to_video(
                    cover_image_path=str(Path(image_handoff_dir) / "cover.png"),
                    scene_images_dir=str(Path(image_handoff_dir) / "scene_images"),
                    manifest_path=str(Path(image_handoff_dir) / "manifest.json"),
                ),
                success_message="Sent the handoff naming bundle to Video.",
            ),
        ])
    render_handoff_action_row(handoff_actions, column_spec=[1.0] * len(handoff_actions))

    render_download_button_row(
        [
            DownloadSpec(
                "Download canonical JSON",
                data=json.dumps(result.get("authoring"), ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="story_authoring.json",
                mime="application/json",
                key="download_story_canonical_json_btn",
            ),
            DownloadSpec(
                "Download result ZIP",
                data=bundle_bytes,
                file_name="story_output_bundle.zip",
                mime="application/zip",
                key="download_story_bundle_zip_btn",
            ),
        ],
        column_spec=[1.0, 1.1],
    )

    if prompts_ready:
        render_download_button_row(
            [
                DownloadSpec(
                    "Download cover prompt",
                    data=dumps_json((result.get("image_prompts") or {}).get("cover") or {}),
                    file_name="cover_prompt.json",
                    mime="application/json",
                    key="download_story_cover_prompt_btn",
                ),
                DownloadSpec(
                    "Download scene overview prompt",
                    data=dumps_json((result.get("image_prompts") or {}).get("scene") or {}),
                    file_name="scene_prompt.json",
                    mime="application/json",
                    key="download_story_scene_prompt_btn",
                ),
            ],
            column_spec=[1.0, 1.0],
        )
    else:
        st.info("Image prompts have not been created yet. Run Generate image prompts to enable Image/Video handoff.")
    if plain_script_path or canonical_json_path:
        st.caption(f"Saved outputs: {plain_script_path or '-'} | {canonical_json_path or '-'}")
    st.caption(f"Handoff bundle: {image_handoff_dir or '-'}")

def render_preview_tab() -> None:
    result = st.session_state.get("story_last_result")
    failed_result = st.session_state.get("story_last_failed_result")
    outline_result = st.session_state.get("story_outline_result")
    draft_result = st.session_state.get("story_authoring_draft")
    error_context = st.session_state.get("story_last_error_context") or {}
    preview_result = result or failed_result
    if outline_result:
        st.subheader("Story outline")
        st.json(outline_result.get("outline_payload"))
    if draft_result:
        st.subheader("Story draft")
        st.json(draft_result.get("authoring"))
    if preview_result:
        st.subheader("Canonical JSON")
        st.json(preview_result.get("authoring"))
        if error_context.get("script_item") is not None:
            item_index = error_context.get("item_index")
            st.subheader(f"Failed item - script[{item_index}]")
            st.json(error_context.get("script_item"))
            if error_context.get("preview"):
                st.caption(f"Failed text preview: {error_context.get('preview')}")
            if error_context.get("script_excerpt"):
                st.code("\n".join(error_context.get("script_excerpt") or []))
        st.subheader("Plain script")
        st.code(preview_result.get("plain_script") or "")
        if error_context.get("plain_excerpt"):
            st.subheader("Highlighted failed line")
            st.code("\n".join(error_context.get("plain_excerpt") or []))
        if error_context.get("raw_response_excerpt"):
            st.subheader("Raw LLM response excerpt")
            st.code(str(error_context.get("raw_response_excerpt") or ""))
        if result and result.get("canonical_errors"):
            st.subheader("Canonical errors")
            st.code("\n".join(result.get("canonical_errors") or []))
        if result and result.get("image_prompts"):
            st.subheader("Image prompts")
            st.json(result.get("image_prompts"))
    if st.session_state.get("story_last_error"):
        st.subheader("Error")
        st.code(st.session_state.get("story_last_error") or "")


def _render_validation_result(result: Any) -> None:
    st.write(f"OK: {'Yes' if getattr(result, 'ok', False) else 'No'}")
    errors = [f"L{item.line_no}: {item.message}" for item in getattr(result, 'errors', [])]
    warnings = [f"L{item.line_no}: {item.message}" for item in getattr(result, 'warnings', [])]
    if errors:
        st.error("\n".join(errors[:40]))
    else:
        st.success("No validation errors.")
    if warnings:
        st.warning("\n".join(warnings[:40]))
    stats = getattr(result, 'stats', None)
    if stats is not None:
        with st.expander("Validation stats", expanded=False):
            st.json(getattr(stats, '__dict__', {}))


def render_tools_tab(settings: dict[str, Any]) -> None:
    del settings
    tab_convert, tab_canonical, tab_validate_canonical, tab_validate = st.tabs([
        "Convert raw -> plain",
        "Canonical -> plain",
        "Validate canonical",
        "Validate plain",
    ])

    with tab_convert:
        raw_text = st.text_area("Raw story text", key="story_tool_raw_text", height=260)
        title_hint = st.text_input("Title hint", key="story_tool_title_hint")
        col1, col2, col3 = st.columns(3)
        default_voice = col1.selectbox("Default voice", ["NARRATOR", "FEMALE", "MALE"], key="story_tool_default_voice")
        default_speed = col2.selectbox("Default speed", ["NORMAL", "SLOW", "FAST"], key="story_tool_default_speed")
        default_lang = col3.selectbox("Default lang", ["VI", "EN"], key="story_tool_default_lang")
        opt1, opt2, opt3 = st.columns(3)
        add_header = opt1.checkbox("Add header if missing", value=True, key="story_tool_add_header")
        auto_en = opt2.checkbox("Auto detect English", value=True, key="story_tool_auto_en")
        strip_prefix = opt3.checkbox("Strip speaker prefix", value=True, key="story_tool_strip_prefix")
        if st.button("Convert raw -> plain", key="story_tool_convert_btn", width="stretch"):
            if not str(raw_text or "").strip():
                show_missing_input("raw story text", hint="Paste raw content before converting.")
            else:
                output = convert_text(
                    raw_text,
                    add_header_if_missing=bool(add_header),
                    title_hint=str(title_hint or ""),
                    default_voice_role=str(default_voice).lower(),
                    default_speed=str(default_speed).upper(),
                    default_lang=str(default_lang).upper(),
                    auto_en=bool(auto_en),
                    speaker_cfg=SpeakerConfig.default(),
                    strip_prefix=bool(strip_prefix),
                )
                st.session_state["story_tool_plain_output"] = output
                st.success("Converted raw text to plain script.")
        converted = st.session_state.get("story_tool_plain_output", "")
        if converted:
            st.text_area("Converted plain script", value=converted, height=260, key="story_tool_plain_output_view")

    with tab_canonical:
        canonical_text = st.text_area("Canonical JSON", key="story_tool_canonical_text", height=260)
        if st.button("Canonical -> plain", key="story_tool_canonical_btn", width="stretch"):
            if not str(canonical_text or "").strip():
                show_missing_input("canonical JSON", hint="Paste canonical JSON before converting.")
            else:
                try:
                    authoring = json.loads(canonical_text)
                    errors = validate_canonical_authoring(authoring)
                    if errors:
                        st.error("\n".join(errors[:40]))
                    else:
                        plain_text = render_plain_script(authoring)
                        st.session_state["story_tool_canonical_plain_output"] = plain_text
                        st.success("Converted canonical JSON to plain script.")
                except Exception as exc:
                    render_user_message(UserMessage(level="error", title="Canonical -> plain failed", body="Could not read or convert the current canonical JSON.", technical_details=str(exc)), show_details=True)
        converted = st.session_state.get("story_tool_canonical_plain_output", "")
        if converted:
            st.text_area("Plain script from canonical", value=converted, height=260, key="story_tool_canonical_plain_view")

    with tab_validate_canonical:
        canonical_text = st.text_area("Canonical JSON to validate", key="story_tool_validate_canonical_text", height=300)
        show_repair_log = st.checkbox("Show repair log", key="story_tool_validate_canonical_show_repair_log")
        if st.button("Validate canonical JSON", key="story_tool_validate_canonical_btn", width="stretch"):
            if not str(canonical_text or "").strip():
                show_missing_input("canonical JSON", hint="Paste canonical JSON before validating.")
            else:
                try:
                    authoring = json.loads(canonical_text)
                    errors = validate_canonical_authoring(authoring)
                    errors.extend(validate_script_length_rule(authoring))
                    repair_log = extract_auto_repair_log(authoring)
                    st.session_state["story_tool_validate_canonical_result"] = {
                        "ok": not errors,
                        "errors": errors,
                        "auto_repair_log_count": len(repair_log),
                        "auto_repair_log": repair_log,
                    }
                except Exception as exc:
                    render_user_message(
                        UserMessage(
                            level="error",
                            title="Canonical validation failed",
                            body="Could not read the current canonical JSON.",
                            technical_details=str(exc),
                        ),
                        show_details=True,
                    )
        canonical_result = st.session_state.get("story_tool_validate_canonical_result")
        if isinstance(canonical_result, dict):
            if canonical_result.get("ok"):
                st.success("Canonical authoring is valid.")
            else:
                st.error("\n".join([str(item) for item in canonical_result.get("errors", [])][:40]))
            st.metric("Auto-repair entries", int(canonical_result.get("auto_repair_log_count") or 0))
            if show_repair_log and canonical_result.get("auto_repair_log"):
                with st.expander("Auto-repair log", expanded=True):
                    st.json(canonical_result.get("auto_repair_log"))

    with tab_validate:
        plain_text = st.text_area("Plain script to validate", key="story_tool_validate_plain_text", height=320)
        if st.button("Validate plain script", key="story_tool_validate_btn", width="stretch"):
            if not str(plain_text or "").strip():
                show_missing_input("plain script", hint="Paste plain script before validating.")
            else:
                st.session_state["story_tool_validate_result"] = validate_script(str(plain_text).splitlines())
        result = st.session_state.get("story_tool_validate_result")
        if result is not None:
            _render_validation_result(result)




def render_doctor_tab(settings: dict[str, Any]) -> None:
    st.subheader("Story doctor")
    diagnostics = collect_runtime_diagnostics()
    llm_status = current_llm_status(settings)
    handoff = workspace_source_outputs(st.session_state)

    c1, c2, c3 = st.columns(3)
    c1.metric("LLM provider", str(settings.get("llm_provider_label") or settings.get("llm_provider") or "-"))
    c2.metric("Model", str(settings.get("model") or "-")[:40])
    c3.metric("LLM status", str(llm_status.get("state") or "unknown"))

    state = str(llm_status.get("state") or "unknown").lower()
    message = f"{llm_status.get('label') or '-'} - {llm_status.get('detail') or '-'}"
    if state == "ok":
        st.success(message)
    elif state in {"stale", "unknown"}:
        st.info(message)
    else:
        st.warning(message)

    rows = [
        {"check": "Brief text", "status": "OK" if str(st.session_state.get("story_brief_text") or "").strip() else "missing", "detail": "Brief entered" if str(st.session_state.get("story_brief_text") or "").strip() else "No brief text yet."},
        {"check": "System prompt", "status": "OK" if str(st.session_state.get("story_system_prompt_text") or "").strip() else "missing", "detail": "System prompt entered" if str(st.session_state.get("story_system_prompt_text") or "").strip() else "No system prompt yet."},
        {"check": "Story output", "status": "OK" if str(handoff.story_plain_script_path or "").strip() else "missing", "detail": str(handoff.story_plain_script_path or "No latest plain script output file yet.")},
    ]
    st.markdown("#### Story readiness")
    st.dataframe(rows, width="stretch", height=180)
    render_runtime_diagnostics_block({
        "settings": {
            "provider": settings.get("llm_provider"),
            "provider_label": settings.get("llm_provider_label"),
            "profile": settings.get("llm_profile"),
            "base_url": settings.get("base_url"),
            "model": settings.get("model"),
            "timeout_s": settings.get("timeout_s"),
            "max_tokens": settings.get("max_tokens"),
            "temperature": settings.get("temperature"),
            "retries": settings.get("retries"),
            "chunked": settings.get("chunked"),
            "chunk_size": settings.get("chunk_size"),
        },
        "llm_status": llm_status,
    }, label="Current Story settings", expanded=False)
    render_runtime_diagnostics_block(diagnostics, label="Raw runtime diagnostics", expanded=False)


def render_history_tab() -> None:
    items = st.session_state.get("story_last_history", [])
    render_session_history(
        items,
        empty_message="No generation history in the current session yet.",
        title_builder=lambda idx, item: f"#{idx} - {item.get('title')}",
    )


def render_test_llm_tab(settings: dict[str, Any]) -> None:
    render_llm_test_panel(settings)


def render_preview_logs_tab(settings: dict[str, Any]) -> None:
    del settings
    render_preview_tab()
    st.divider()
    st.subheader("History")
    render_history_tab()
