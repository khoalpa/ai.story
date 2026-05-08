from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from audio.gui.workspace_state import append_global_run_event, get_workspace_target_field, send_audio_to_video, set_audio_handoff, update_global_run_monitor
from audio.gui.workspace_source_outputs import workspace_source_outputs

from audio.exceptions import AudioStoryError
from audio.render_job_repository import JobRepository

from .helpers import (
    ProgressCollector,
    build_output_zip,
    make_request,
    normalize_plain_script_text,
    output_download_name,
)
from .service import _preview_voice_rate, _preview_voice_role, _preview_voice_speed_key, format_runtime_error, preview_tts_sample, run_audio_job, summarize_audio_job, validate_plain_text, validate_provider_runtime_settings
from audio.tts_provider import get_tts_provider_choices, get_tts_provider_descriptor
from audio.voice_catalog import get_voice_choices, resolve_voice_selection

from audio.services.render_runtime import build_voice_maps, resolve_runtime_context
from .view_models import build_audio_run_summary
from .workspace import render_workspace_tab
from audio.gui.user_messages import UserMessage, render_user_message, show_missing_input, show_preview_warning



def _apply_pending_run_plain_text() -> None:
    pending = st.session_state.pop("pending_run_plain_text", None)
    if pending is not None:
        st.session_state["last_plain_script"] = pending
        st.session_state["run_plain_text"] = pending


def _apply_story_handoff_prefill_to_run() -> None:
    incoming = st.session_state.get("workspace_story_plain_script_text", "") or ""
    previous_auto = st.session_state.get("audio_last_auto_plain_script", "") or ""
    current_run = st.session_state.get("run_plain_text", "") or ""
    lock_to_handoff = bool(st.session_state.get("audio_lock_to_story_handoff", False))
    if not incoming or incoming == previous_auto:
        return
    if lock_to_handoff or not current_run or current_run == previous_auto:
        st.session_state["run_plain_text"] = incoming
        st.session_state["last_plain_script"] = incoming
    st.session_state["audio_last_auto_plain_script"] = incoming


def render_preview_table() -> None:
    segments = st.session_state.get("last_preview_segments", [])
    if not segments:
        show_preview_warning(
            "segment preview",
            reason="Run validate or render first to build the segment list.",
            actions=["Open the Run tab and use Quick Validate or Run pipeline.", "Return to the preview table after new results are available."],
        )
        return

    rows = []
    for idx, seg in enumerate(segments, start=1):
        rows.append(
            {
                "#": idx,
                "voice": getattr(seg, "voice", ""),
                "lang": getattr(seg, "lang", ""),
                "zone": getattr(seg, "zone", ""),
                "env": getattr(seg, "env", ""),
                "bgm": getattr(seg, "bgm", ""),
                "ambience": getattr(seg, "ambience", ""),
                "rate": getattr(seg, "rate", ""),
                "pause_before_ms": getattr(seg, "pause_ms_before", 0),
                "text": getattr(seg, "text", ""),
            }
        )
    st.dataframe(rows, width="stretch", height=420)



def _audio_download_meta(out_file: str | None, summary: dict) -> tuple[str, str]:
    path = Path(out_file) if out_file else None
    ext = path.suffix.lower() if path else ""
    fmt = str(summary.get("audio_format", "")).strip().lower()

    if ext == ".wav" or fmt == "wav":
        return "Download WAV", "audio/wav"
    return "Download MP3", "audio/mpeg"



def render_output_downloads(summary: dict) -> None:
    out_file = summary.get("out_file")
    srt_path = summary.get("srt_path")
    debug_json = summary.get("debug_json")

    col1, col2, col3 = st.columns(3)
    with col1:
        if out_file and Path(out_file).is_file():
            label, mime = _audio_download_meta(out_file, summary)
            st.audio(out_file)
            st.download_button(
                label,
                data=Path(out_file).read_bytes(),
                file_name=Path(out_file).name,
                mime=mime,
                width="stretch",
            )
    with col2:
        if srt_path and Path(srt_path).is_file():
            st.download_button(
                "Download SRT",
                data=Path(srt_path).read_bytes(),
                file_name=Path(srt_path).name,
                mime="text/plain",
                width="stretch",
            )
    with col3:
        if debug_json and Path(debug_json).is_file():
            st.download_button(
                "Download Debug JSON",
                data=Path(debug_json).read_bytes(),
                file_name=Path(debug_json).name,
                mime="application/json",
                width="stretch",
            )

    bundle = build_output_zip(summary)
    if bundle is not None:
        st.download_button(
            "Download output bundle (.zip)",
            data=bundle,
            file_name=output_download_name(),
            mime="application/zip",
            width="stretch",
        )


def _render_final_segment_rate_debug() -> None:
    segments = st.session_state.get("last_preview_segments", [])
    if not segments:
        return

    rows = []
    for idx, seg in enumerate(segments, start=1):
        text = str(getattr(seg, "text", "") or "").strip()
        rows.append(
            {
                "#": idx,
                "voice": getattr(seg, "voice", ""),
                "lang": getattr(seg, "lang", ""),
                "rate": getattr(seg, "rate", ""),
                "pause_before_ms": getattr(seg, "pause_ms_before", 0),
                "text": text[:96] + ("..." if len(text) > 96 else ""),
            }
        )

    with st.expander("Final segment rates", expanded=False):
        st.caption("This is the final per-segment rate after all defaults, tags, and sentiment/preset adjustments.")
        st.dataframe(rows, width="stretch", height=260)



def run_single_job(plain_text: str, settings: dict, repository: JobRepository) -> None:  # noqa: ARG001
    if not plain_text.strip():
        show_missing_input(
            "plain script",
            hint="Prepare content in the Input tab, then try again.",
            actions=["Paste the plain script directly into Run, or use the sync button from Input.", "Run the pipeline again after the content is ready."],
        )
        return

    normalized_text, normalized = normalize_plain_script_text(plain_text)
    if normalized:
        st.session_state["last_plain_script"] = normalized_text
        render_user_message(
            UserMessage(
                level="info",
                title="Plain script normalized",
                body="The GUI automatically added the SCRIPT: line before running.",
            )
        )

    status_slot = st.empty()
    progress_slot = st.empty()
    event_slot = st.empty()
    log_slot = st.empty()

    collector = ProgressCollector(status_slot, progress_slot, event_slot, log_slot)

    update_global_run_monitor(app="Audio", stage="Render", status="running", progress=10, summary={"mode": settings.get("mode"), "audio_format": settings.get("audio_format")})
    append_global_run_event(app="Audio", stage="Render", status="running", message=f"mode={settings.get('mode')} format={settings.get('audio_format')}")

    try:
        validate_provider_runtime_settings(settings)
        result = run_audio_job(
            plain_text=normalized_text,
            settings=settings,
            repository=repository,
            event_sink=collector,
        )
    except (AudioStoryError, OSError, ValueError) as exc:
        error_text = format_runtime_error(exc)
        update_global_run_monitor(app="Audio", stage="Render", status="failed", progress=100, error_text=error_text, summary={"mode": settings.get("mode"), "audio_format": settings.get("audio_format")})
        append_global_run_event(app="Audio", stage="Render", status="failed", message="Audio job failed", error_text=error_text)
        status_slot.error(error_text)
        st.session_state["last_event_log"] = collector.events
        return

    summary = summarize_audio_job(result)
    st.session_state["last_result_summary"] = summary
    st.session_state["last_preview_segments"] = list(result.preview.segments) if result.preview else []
    st.session_state["last_event_log"] = collector.events
    outputs = workspace_source_outputs(st.session_state)
    outputs.audio_output = str(summary.get("out_file") or "")
    outputs.audio_srt_output = str(summary.get("srt_path") or "")
    update_global_run_monitor(
        app="Audio",
        stage="Render",
        status="completed" if result.mode != "validate_only" or not result.validate_exit_code else "failed",
        progress=100,
        output_path=workspace_source_outputs(st.session_state).audio_output,
        error_text="\n".join(summary.get("validate_errors") or []),
        summary=summary,
    )
    append_global_run_event(
        app="Audio",
        stage="Render",
        status="completed" if result.mode != "validate_only" or not result.validate_exit_code else "failed",
        message=f"segments={summary.get('segment_count') or 0} format={summary.get('audio_format') or '-'}",
        output_path=workspace_source_outputs(st.session_state).audio_output,
        error_text="\n".join(summary.get("validate_errors") or []),
    )
    set_audio_handoff(
        audio_output_path=workspace_source_outputs(st.session_state).audio_output,
        srt_output_path=workspace_source_outputs(st.session_state).audio_srt_output,
    )
    progress_slot.progress(1.0, text="100% - Complete")
    if result.mode == "validate_only":
        if result.validate_exit_code:
            status_slot.error("Validation failed")
        else:
            status_slot.success("Validate succeeded")
    else:
        status_slot.success(f"Run completed in mode: {result.mode}")

    st.json(summary)
    _render_final_segment_rate_debug()
    if summary.get("validate_errors"):
        render_user_message(
            UserMessage(
                level="error",
                title="Validation failed",
                body=f"Detected {len(summary.get('validate_errors') or [])} error(s) in the plain script. Open the details section to inspect each one.",
                technical_details="\n".join(summary.get("validate_errors") or []),
            ),
            show_details=True,
        )



def _preview_voice_options(provider: str, lang: str) -> tuple[list[str], dict[str, str]]:
    ordered_values: list[str] = []
    labels: dict[str, str] = {}
    for role in ("narrator", "female", "male"):
        for item in get_voice_choices(tts_provider=provider, lang=lang, role=role):
            value = str(item.value or "").strip()
            if not value or value in labels:
                continue
            ordered_values.append(value)
            labels[value] = str(item.label or value)
    return ordered_values, labels


def _render_tts_preview_card(settings: dict) -> None:
    st.subheader("Voice preview")
    st.caption("Preview a sentence with the selected TTS provider and voice before rendering the full run.")

    preview_text = st.text_input(
        "Preview sentence",
        key="preview_tts_text",
    )
    default_provider = str(st.session_state.get("preview_tts_provider") or settings.get("tts_provider") or "")
    provider_options = get_tts_provider_choices()
    if default_provider not in provider_options:
        default_provider = provider_options[0] if provider_options else "edge"
    provider_index = provider_options.index(default_provider) if default_provider in provider_options else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        preview_provider = st.selectbox("TTS provider", provider_options, index=provider_index, key="preview_tts_provider")
    with col2:
        preview_lang = st.selectbox("Language", ["vi", "en"], key="preview_tts_lang")
    preview_voice_values, preview_voice_labels = _preview_voice_options(preview_provider, preview_lang)
    default_voice = str(
        st.session_state.get("preview_tts_voice")
        or (settings.get("voice_en_narrator") if preview_lang == "en" else settings.get("voice_narrator"))
        or ""
    ).strip()
    selected_voice = resolve_voice_selection(
        default_voice,
        tts_provider=preview_provider,
        lang=preview_lang,
        role="narrator",
        fallback=preview_voice_values[0] if preview_voice_values else default_voice,
    )
    with col3:
        if preview_voice_values:
            default_index = preview_voice_values.index(selected_voice) if selected_voice in preview_voice_values else 0
            preview_voice = st.selectbox(
                "Voice selection",
                options=preview_voice_values,
                index=default_index,
                format_func=lambda value: preview_voice_labels.get(value, value),
                key="preview_tts_voice",
            )
        else:
            preview_voice = st.text_input("Voice selection", value=selected_voice, key="preview_tts_voice")
    inferred_role = _preview_voice_role(preview_provider, preview_lang, preview_voice)
    speed_key = _preview_voice_speed_key(preview_lang, inferred_role)
    speed_value = _preview_voice_rate(settings, preview_lang, inferred_role)
    st.caption(f"Preview role: `{inferred_role}` | speed source: `{speed_key}` = `{speed_value}`")
    with col4:
        if st.button("Preview one sentence", width="stretch"):
            try:
                audio_path = preview_tts_sample(
                    text=preview_text,
                    settings=settings,
                    lang=preview_lang,
                    voice_choice=preview_voice,
                    provider_override=preview_provider,
                )
            except (AudioStoryError, OSError, ValueError) as exc:
                st.session_state["last_preview_audio_error"] = format_runtime_error(exc)
                st.session_state["last_preview_audio_path"] = ""
            else:
                st.session_state["last_preview_audio_error"] = ""
                st.session_state["last_preview_audio_path"] = str(audio_path)


    provider_desc = get_tts_provider_descriptor(preview_provider)
    st.caption(f"Current preview provider: {provider_desc.label} - {provider_desc.description}")
    if preview_provider != str(settings.get("tts_provider") or ""):
        render_user_message(
            UserMessage(
                level="info",
                title="TTS preview is using a separate provider",
                body="Default voice and detailed config still come from the current sidebar state, so double-check the voice ID if you switch to another provider.",
            )
        )

    preview_error = st.session_state.get("last_preview_audio_error", "")
    if preview_error:
        render_user_message(
            UserMessage(
                level="error",
                title="Could not create preview audio",
                body="TTS preview failed. Check the provider, voice, and runtime config before trying again.",
                technical_details=str(preview_error),
            ),
            show_details=True,
        )
    preview_audio_path = st.session_state.get("last_preview_audio_path", "")
    if preview_audio_path and Path(preview_audio_path).is_file():
        audio_file = Path(preview_audio_path)
        st.audio(str(audio_file))
        st.download_button(
            "Download preview WAV",
            data=audio_file.read_bytes(),
            file_name=audio_file.name,
            mime="audio/wav",
            width="stretch",
        )



def render_input_tab() -> None:
    render_workspace_tab()


def render_test_tts_tab(settings: dict) -> None:
    _render_tts_preview_card(settings)




def _describe_runtime_voice_source(configured_value: str, runtime_value: str, profile_defaults: dict[str, str], *profile_keys: str) -> str:
    if configured_value == runtime_value:
        return "GUI/default"
    for key in profile_keys:
        candidate = str(profile_defaults.get(key) or "").strip()
        if candidate and candidate == runtime_value:
            return f"profile:{key}"
    return "runtime override"


def _settings_to_payload(settings: object) -> dict:
    if settings is None:
        return {}
    if isinstance(settings, dict):
        return dict(settings)
    to_payload = getattr(settings, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    get_payload = getattr(settings, "get", None)
    if callable(get_payload):
        try:
            probe_keys = (
                "tts_provider",
                "vieneu_core",
                "vieneu_mode",
                "vieneu_api_base",
                "vieneu_model_name",
                "voice_narrator",
                "voice_female",
                "voice_male",
                "voice_en_narrator",
                "voice_en_female",
                "voice_en_male",
                "voice_narrator_speed",
                "voice_female_speed",
                "voice_male_speed",
                "voice_en_narrator_speed",
                "voice_en_female_speed",
                "voice_en_male_speed",
                "output_dir",
                "audio_format",
                "mode",
            )
            return {key: get_payload(key) for key in probe_keys if get_payload(key) is not None}
        except Exception:
            return {}
    return {}



def _build_runtime_preview_settings(settings: object) -> dict:
    merged = _settings_to_payload(settings)
    live_key_aliases = {
        "tts_provider": ("tts_provider",),
        "vieneu_core": ("vieneu_core",),
        "vieneu_mode": ("vieneu_mode",),
        "vieneu_api_base": ("vieneu_api_base",),
        "vieneu_model_name": ("vieneu_model_name",),
        "voice_narrator": ("voice_narrator", "voice_vi_narrator"),
        "voice_female": ("voice_female", "voice_vi_female"),
        "voice_male": ("voice_male", "voice_vi_male"),
        "voice_en_narrator": ("voice_en_narrator", "voice_en_narrator_key"),
        "voice_en_female": ("voice_en_female", "voice_en_female_key"),
        "voice_en_male": ("voice_en_male", "voice_en_male_key"),
        "voice_narrator_speed": ("voice_narrator_speed",),
        "voice_female_speed": ("voice_female_speed",),
        "voice_male_speed": ("voice_male_speed",),
        "voice_en_narrator_speed": ("voice_en_narrator_speed",),
        "voice_en_female_speed": ("voice_en_female_speed",),
        "voice_en_male_speed": ("voice_en_male_speed",),
    }
    for canonical_key, session_keys in live_key_aliases.items():
        for session_key in session_keys:
            if session_key in st.session_state:
                value = st.session_state.get(session_key)
                if value is not None:
                    merged[canonical_key] = value
                    break
    return merged



def _resolve_runtime_voice_preview(settings: dict) -> tuple[dict[str, object] | None, str | None]:
    try:
        preview_settings = _build_runtime_preview_settings(settings)
        request = make_request(
            input_path=Path("runtime_voice_preview.txt"),
            output_dir=Path(str(preview_settings.get("output_dir") or ".")),
            settings=preview_settings,
        )
        args = request.to_namespace()
        runtime_ctx = resolve_runtime_context(args)
        voice_maps = build_voice_maps(args, runtime_ctx.profile_voice_defaults)
        profile_defaults = dict(runtime_ctx.profile_voice_defaults or {})
        rows = [
            {
                "slot": "VI narrator",
                "gui": str(request.voice_narrator),
                "runtime": str(voice_maps.voice_map_vi.get("narrator") or ""),
                "source": _describe_runtime_voice_source(
                    str(request.voice_narrator),
                    str(voice_maps.voice_map_vi.get("narrator") or ""),
                    profile_defaults,
                    "vi_narrator",
                    "voice_narrator",
                ),
            },
            {
                "slot": "VI female",
                "gui": str(request.voice_female),
                "runtime": str(voice_maps.voice_map_vi.get("female") or ""),
                "source": _describe_runtime_voice_source(
                    str(request.voice_female),
                    str(voice_maps.voice_map_vi.get("female") or ""),
                    profile_defaults,
                    "vi_female",
                    "voice_female",
                ),
            },
            {
                "slot": "VI male",
                "gui": str(request.voice_male),
                "runtime": str(voice_maps.voice_map_vi.get("male") or ""),
                "source": _describe_runtime_voice_source(
                    str(request.voice_male),
                    str(voice_maps.voice_map_vi.get("male") or ""),
                    profile_defaults,
                    "vi_male",
                    "voice_male",
                ),
            },
            {
                "slot": "EN narrator",
                "gui": str(request.voice_en_narrator),
                "runtime": str(voice_maps.voice_map_en.get("narrator") or ""),
                "source": _describe_runtime_voice_source(
                    str(request.voice_en_narrator),
                    str(voice_maps.voice_map_en.get("narrator") or ""),
                    profile_defaults,
                    "en_narrator",
                    "voice_en_narrator",
                ),
            },
            {
                "slot": "EN female",
                "gui": str(request.voice_en_female),
                "runtime": str(voice_maps.voice_map_en.get("female") or ""),
                "source": _describe_runtime_voice_source(
                    str(request.voice_en_female),
                    str(voice_maps.voice_map_en.get("female") or ""),
                    profile_defaults,
                    "en_female",
                    "voice_en_female",
                ),
            },
            {
                "slot": "EN male",
                "gui": str(request.voice_en_male),
                "runtime": str(voice_maps.voice_map_en.get("male") or ""),
                "source": _describe_runtime_voice_source(
                    str(request.voice_en_male),
                    str(voice_maps.voice_map_en.get("male") or ""),
                    profile_defaults,
                    "en_male",
                    "voice_en_male",
                ),
            },
        ]
        payload = {
            "provider": str(getattr(request, "tts_provider", "") or ""),
            "vieneu_mode": str(getattr(request, "vieneu_mode", "") or ""),
            "vieneu_model_name": str(getattr(request, "vieneu_model_name", "") or ""),
            "asset_profile": str(getattr(request, "asset_profile", "") or ""),
            "rows": rows,
            "vi_effective": {
                "narrator": str(voice_maps.voice_map_vi.get("narrator") or ""),
                "female": str(voice_maps.voice_map_vi.get("female") or ""),
                "male": str(voice_maps.voice_map_vi.get("male") or ""),
            },
            "en_effective": {
                "narrator": str(voice_maps.voice_map_en.get("narrator") or ""),
                "female": str(voice_maps.voice_map_en.get("female") or ""),
                "male": str(voice_maps.voice_map_en.get("male") or ""),
            },
        }
        return payload, None
    except Exception as exc:
        return None, format_runtime_error(exc)


def _render_audio_focus_hint() -> None:
    if st.session_state.get("workspace_active_app") != "Audio":
        return
    if st.session_state.get("audio_embedded_view_selector") != "Run":
        return
    target_field = str(get_workspace_target_field("Audio", "") or "").strip()
    if not target_field:
        return
    mapping = {"plain_script": "Plain script", "doctor": "Audio Doctor"}
    st.info(f"Deep-link target: {mapping.get(target_field, target_field)}")

def render_run_tab(settings: dict, repository: JobRepository) -> None:
    _apply_pending_run_plain_text()
    _apply_story_handoff_prefill_to_run()

    _render_audio_focus_hint()

    if not st.session_state.get("run_plain_text"):
        st.session_state["run_plain_text"] = (st.session_state.get("last_plain_script") or st.session_state.get("plain_script_text") or "")

    with st.expander("Run configuration summary", expanded=False):
        st.json(build_audio_run_summary(settings))
        diagnostics = settings.get("runtime_diagnostics")
        if diagnostics:
            st.caption("Runtime")
            st.json(diagnostics.as_dict())

    plain_text = st.text_area(
        "Script used for this run",
        height=340,
        key="run_plain_text",
    )
    st.session_state["last_plain_script"] = plain_text

    st.caption("Final runtime voice mapping after merging GUI settings and asset profile")
    runtime_voice_preview, runtime_voice_error = _resolve_runtime_voice_preview(settings)
    if runtime_voice_preview:
        provider = str(runtime_voice_preview.get("provider") or "").strip().lower()
        effective_mode = str(runtime_voice_preview.get("vieneu_mode") or "").strip() or "-"
        effective_model = str(runtime_voice_preview.get("vieneu_model_name") or "").strip() or "-"
        vi_effective = dict(runtime_voice_preview.get("vi_effective") or {})
        en_effective = dict(runtime_voice_preview.get("en_effective") or {})
        rows = list(runtime_voice_preview.get("rows") or [])

        if provider == "vieneu":
            st.markdown("\n".join(
                    [
                        "**Effective VieNeu mode**",
                        f"- mode: `{effective_mode}`",
                        f"- model: `{effective_model}`",
                        f"- VI map: narrator=`{vi_effective.get('narrator', '')}`, female=`{vi_effective.get('female', '')}`, male=`{vi_effective.get('male', '')}`",
                        f"- EN map: narrator=`{en_effective.get('narrator', '')}`, female=`{en_effective.get('female', '')}`, male=`{en_effective.get('male', '')}`",
                    ]
                )
            )
        else:
            st.markdown("\n".join(
                    [
                        "**Effective TTS runtime**",
                        f"- provider: `{provider or '-'}`",
                        "- VieNeu mode: not applicable for the current provider",
                    ]
                )
            )

        st.dataframe(rows, width="stretch", height=248)
    elif runtime_voice_error:
        render_user_message(
            UserMessage(
                level="warning",
                title="Could not resolve runtime voice preview",
                body="The Run tab could not build the final runtime voice preview. The pipeline can still run, but the preview is currently unavailable.",
                technical_details=str(runtime_voice_error),
            ),
            show_details=True,
        )

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("Run pipeline", type="primary", width="stretch"):
            normalized_text, normalized = normalize_plain_script_text(plain_text)
            if normalized:
                st.session_state["pending_run_plain_text"] = normalized_text
            run_single_job(normalized_text, settings, repository)
    with col2:
        if st.button("Quick validate", width="stretch"):
            normalized_text, normalized = normalize_plain_script_text(plain_text)
            if normalized:
                st.session_state["pending_run_plain_text"] = normalized_text
                render_user_message(
                    UserMessage(
                        level="info",
                        title="Plain script normalized",
                        body="The GUI automatically added the SCRIPT: line before validate.",
                    )
                )
            exit_code, errors, warnings = validate_plain_text(normalized_text)
            if exit_code:
                render_user_message(
                    UserMessage(
                        level="error",
                        title="Quick validate failed",
                        body=f"Detected {len(errors)} error(s) in the plain script. Open details to inspect all of them.",
                        technical_details="\n".join(errors),
                    ),
                    show_details=True,
                )
            else:
                st.success(f"Validate OK. Warnings: {warnings}")

    summary = st.session_state.get("last_result_summary")
    if summary:
        st.divider()
        st.subheader("Latest result")
        output_name = summary.get("out_file_name") or Path(str(summary.get("out_file") or "")).name
        if output_name:
            st.caption(f"Output file: {output_name}")
        st.json(summary)

        handoff_cols = st.columns([1.2, 1.0])
        with handoff_cols[0]:
            if st.button("Send to Video", width="stretch", key="send_audio_to_video_btn"):
                send_audio_to_video(
                    audio_output_path=str(summary.get("out_file") or ""),
                    srt_output_path=str(summary.get("srt_path") or ""),
                )
                st.success("Sent Audio output to Video and enabled handoff lock.")
                st.rerun()
        with handoff_cols[1]:
            st.checkbox(
                "Lock Video to Audio handoff",
                key="video_lock_to_audio_handoff",
                help="When enabled, Video keeps following the newest audio/subtitle sent from Audio.",
            )

        render_output_downloads(summary)



def render_preview_tab() -> None:
    summary = st.session_state.get("last_result_summary")
    if summary:
        top = st.columns(4)
        top[0].metric("Segments", summary.get("segment_count") or 0)
        top[1].metric("Estimated duration", summary.get("estimated_duration") or "-")
        top[2].metric("Mode", summary.get("mode") or "-")
        top[3].metric("Audio format", str(summary.get("audio_format") or "-").upper())
    render_preview_table()

    events = st.session_state.get("last_event_log", [])
    if events:
        st.subheader("Event log")
        st.code(json.dumps(events, ensure_ascii=False, indent=2), language="json")
