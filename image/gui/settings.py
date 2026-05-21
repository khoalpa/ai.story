from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from common.gui.diagnostics_blocks import DiagnosticsSection, render_diagnostics_sections
from common.gui.panel_utils import render_json_summary_expander, safe_rerun
from common.gui.provider_actions import (
    ProviderAction,
    render_action_status,
    render_provider_action_row,
    set_action_status,
)
from common.gui.sidebar_sections import SidebarSection
from common.gui.user_messages import (
    GuidanceAction,
    UserMessage,
    render_user_message,
    show_provider_error,
)
from common.model_store import (
    detect_image_model_type,
    list_local_models,
    list_local_targets,
    provider_models_dir,
    provider_target_dir,
)
from image.provider_runtime import (
    local_provider_status,
    parse_comfyui_workflow_preview,
    preload_local_provider,
)
from image.providers import (
    SDProvider,
    get_sd_provider,
    get_sd_provider_choices,
    list_sd_provider_ids,
)
from image.runtime import package_root
from image.workflow_routing import default_comfyui_workflow_file


def _index_or_zero(options: list[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0



def _auto_original_config_for_family(pipeline_family: str) -> str:
    family = str(pipeline_family or "").strip().lower()
    mapping = {
        "sd15": "image/models/configs/v1-inference.yaml",
        "sdxl": "image/models/configs/sdxl-base-inference.yaml",
    }
    return mapping.get(family, "")


def _resolve_workspace_path(path_value: str) -> Path:
    path = Path(str(path_value or "").strip()).expanduser()
    if path.is_absolute():
        return path
    return (package_root(__file__).parent / path).resolve()



def _image_provider_message(level: str, message: str) -> None:
    st.session_state["image_provider_message"] = (level, message)


_DEFAULT_LOCAL_SD_MODEL = get_sd_provider("stable_diffusion_local").default_model
_ADVANCED_PAYLOAD_RENDERERS = {"a1111_remote", "diffusers_local"}


def _provider_supports_advanced_payload(provider: SDProvider) -> bool:
    return provider.renderer in _ADVANCED_PAYLOAD_RENDERERS


def _provider_supports_comfyui_workflow_preview(provider: SDProvider) -> bool:
    return provider.is_comfyui


def _parse_advanced_payload_json(raw_value: str) -> tuple[dict[str, Any], str]:
    text = str(raw_value or "").strip()
    if not text:
        return {}, ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"Advanced payload JSON is invalid: {exc.msg} at line {exc.lineno}, column {exc.colno}."
    if not isinstance(parsed, dict):
        return {}, "Advanced payload JSON must be a JSON object."
    return parsed, ""


def _render_advanced_payload_json(provider_meta: SDProvider) -> tuple[str, dict[str, Any]]:
    if not _provider_supports_advanced_payload(provider_meta):
        st.session_state["image_advanced_payload_json_error"] = ""
        return str(st.session_state.get("image_advanced_payload_json") or ""), {}

    st.subheader("Advanced payload")
    raw_value = st.text_area(
        "Advanced payload JSON",
        value=str(st.session_state.get("image_advanced_payload_json") or ""),
        height=140,
        key="image_advanced_payload_json",
        help=(
            "Optional JSON object merged into the provider payload for A1111 remote or Diffusers local. "
            "Use this for provider-specific options that do not have dedicated controls yet."
        ),
    )
    parsed, error = _parse_advanced_payload_json(raw_value)
    st.session_state["image_advanced_payload_json_error"] = error
    if error:
        render_user_message(
            UserMessage(
                level="error",
                title="Advanced payload JSON is invalid",
                body=error,
                actions=(GuidanceAction("Fix the JSON object or clear the field before generating."),),
            )
        )
        return raw_value, {}
    if parsed:
        st.caption(f"Advanced payload keys: {', '.join(sorted(parsed.keys()))}")
    return raw_value, parsed


def _provider_has(provider: SDProvider, option_group: str) -> bool:
    return option_group in provider.option_groups


def _friendly_local_sd_missing_model_message() -> str:
    return (
        "Stable Diffusion local does not have a model available for testing yet. "
        "Fill in **Local model id / path** before running again. "
        f"Quick suggestion: `{_DEFAULT_LOCAL_SD_MODEL}` or a local folder such as `image/models/sdxl`."
    )


def _validate_provider_before_test(provider: str, settings: dict[str, Any]) -> str | None:
    provider_meta = get_sd_provider(provider)
    if not provider_meta.missing_model_requires_warning:
        return None
    model_ref = str(settings.get("local_model_id_or_path") or "").strip()
    if model_ref:
        return None
    return _friendly_local_sd_missing_model_message()


def _render_target_path_tools(*, label: str, path_value: str, key_prefix: str) -> None:
    path_str = str(path_value or '').strip()
    if not path_str:
        return
    st.text_input(label, value=path_str, disabled=True, key=f"{key_prefix}_target_path_display")
    cols = st.columns(2)
    file_uri = Path(path_str).resolve().as_uri() if path_str else ''
    if hasattr(cols[0], 'link_button') and file_uri:
        cols[0].link_button('Open target folder', file_uri, width="stretch")
    else:
        cols[0].button('Open target folder', disabled=True, key=f"{key_prefix}_open_disabled", width="stretch")
    if cols[1].button('Copy target path', key=f"{key_prefix}_copy_target", width="stretch"):
        _image_provider_message('success', f'Image: target path ready to copy -> {path_str}')


def _render_model_type_hint(*, model_ref: str, mode: str, provider: str, key_prefix: str) -> None:
    hint = detect_image_model_type(model_ref, mode=mode)
    family = str(hint.get('family') or 'unknown')
    variant = str(hint.get('variant') or 'base')
    suggested_mode = str(hint.get('suggested_mode') or mode or 'txt2img')
    provider_hint = str(hint.get('provider_hint') or provider or 'stable_diffusion_local')
    st.caption(f"Detected model type: {family} | variant={variant} | suggested provider={provider_hint} | suggested mode={suggested_mode}")


def _model_target_selector(
    *,
    label: str,
    branch: str,
    provider_id: str,
    current_value: str,
    key_prefix: str,
    max_depth: int = 3,
    placeholder: str = "",
    suggested_default: str = "",
    help_text: str = "",
    preferred_suffixes: tuple[str, ...] = (),
    prefer_first_match_as_default: bool = False,
) -> tuple[str, str]:
    target_dir = provider_target_dir(branch, provider_id, __file__)
    local_targets = list_local_targets(branch, __file__, provider_id=provider_id, max_depth=max_depth)
    preferred_targets = [
        target for target in local_targets
        if not preferred_suffixes or str(target).strip().lower().endswith(tuple(s.lower() for s in preferred_suffixes))
    ]
    default_scanned_target = preferred_targets[0] if preferred_targets else ""
    options = ["(manual)", *local_targets]
    selected_key = f"{key_prefix}_selected_target"
    manual_key = f"{key_prefix}_manual_input"
    manual_pending_key = f"{manual_key}_pending"

    current_path = str(current_value or "").strip().replace("\\", "/")
    current_name = Path(current_path).name if current_path else ""
    expected_prefix = f"{branch}/models/{provider_id}/"
    legacy_expected_prefix = f"models/{branch}/{provider_id}/"
    current_relative = current_path
    if current_path.startswith(expected_prefix):
        current_relative = current_path[len(expected_prefix):]
    elif current_path.startswith(legacy_expected_prefix):
        current_relative = current_path[len(legacy_expected_prefix):]

    selected_value = str(st.session_state.get(selected_key) or "(manual)")
    if prefer_first_match_as_default and selected_value == "(manual)" and not current_path and default_scanned_target:
        selected_value = default_scanned_target
    if current_relative and current_relative in local_targets:
        selected_value = current_relative
    elif current_name and current_name in local_targets:
        selected_value = current_name
    elif current_path and current_path in local_targets:
        selected_value = current_path
    if selected_value not in options:
        selected_value = "(manual)"

    selected_value = st.selectbox(
        f"{label} (scan {branch}/models/{provider_id})",
        options=options,
        index=options.index(selected_value),
        key=selected_key,
    )

    resolved_selected_path = ""
    if selected_value != "(manual)":
        resolved_selected_path = f"{branch}/models/{provider_id}/{selected_value}".replace("\\", "/")

    manual_default = resolved_selected_path or current_path
    pending_manual_value = str(st.session_state.get(manual_pending_key) or "").strip()
    if pending_manual_value:
        manual_default = pending_manual_value
        st.session_state[manual_key] = pending_manual_value
        st.session_state[manual_pending_key] = ""
    if selected_value != "(manual)" and st.session_state.get(manual_key) != manual_default:
        st.session_state[manual_key] = manual_default

    manual_value = st.text_input(
        f"{label} manual",
        value=st.session_state.get(manual_key, manual_default),
        key=manual_key,
        placeholder=placeholder or None,
        help=help_text or None,
    )

    if suggested_default:
        cols = st.columns([1, 2])
        if cols[0].button("Use recommended default", key=f"{key_prefix}_use_default", width="stretch"):
            st.session_state[manual_pending_key] = suggested_default
            safe_rerun()
        cols[1].caption(f"Recommended default: `{suggested_default}`")

    effective = resolved_selected_path if resolved_selected_path else str(manual_value or current_value).strip().replace("\\", "/")

    st.caption(f"Update target: {target_dir}")
    if local_targets:
        st.caption(f"Scanned targets: {', '.join(local_targets[:6])}{' ...' if len(local_targets) > 6 else ''}")
    else:
        st.caption("Scanned targets: -")

    return effective, str(target_dir)



def _apply_parsed_values_to_current_preset(preview: dict[str, Any]) -> list[str]:
    applied: list[str] = []
    mapping = {
        "width": "image_width",
        "height": "image_height",
        "steps": "image_steps",
        "cfg": "image_cfg",
        "sampler_name": "image_sampler_name",
        "scheduler": "image_scheduler",
        "seed": "image_seed",
        "local_model_id_or_path": "image_local_model_id_or_path",
        "detected_mode": "image_local_generation_mode",
    }
    for src, dst in mapping.items():
        value = preview.get(src)
        if value is None or value == "":
            continue
        st.session_state[dst] = value
        applied.append(dst)

    controlnet_models = preview.get("controlnet_models") or []
    if controlnet_models:
        first = str((controlnet_models[0] or {}).get("name") or "").strip()
        if first:
            st.session_state["image_local_controlnet_model_id_or_path"] = first
            applied.append("image_local_controlnet_model_id_or_path")

    image_inputs = preview.get("image_inputs") or []
    if image_inputs:
        first_image = str((image_inputs[0] or {}).get("name") or "").strip()
        if first_image:
            mode = str(preview.get("detected_mode") or "")
            if mode == "inpaint":
                st.session_state["image_local_inpaint_image"] = first_image
                applied.append("image_local_inpaint_image")
            else:
                st.session_state["image_local_init_image"] = first_image
                applied.append("image_local_init_image")

    mask_inputs = preview.get("mask_inputs") or []
    if mask_inputs:
        first_mask = str((mask_inputs[0] or {}).get("name") or "").strip()
        if first_mask:
            st.session_state["image_local_inpaint_mask"] = first_mask
            applied.append("image_local_inpaint_mask")
    return applied


def _render_comfyui_workflow_preview(*, label: str, workflow_file: str, key_prefix: str) -> None:
    workflow_path = str(workflow_file or '').strip()
    if not workflow_path:
        st.caption(f"{label}: no workflow JSON is configured yet.")
        return
    with st.expander(f"Workflow parsed result | {label}", expanded=False):
        try:
            preview = parse_comfyui_workflow_preview(workflow_path)
        except Exception as exc:
            show_provider_error("Workflow parser", problem=f"Could not read workflow {label}.", technical_details=f"{type(exc).__name__}: {exc}", show_details=False, actions=["Check the workflow path or the JSON content again.", "Try another workflow and parse it again."])
            return
        c1, c2 = st.columns(2)
        c1.markdown(f"**Mode:** `{preview.get('detected_mode') or 'txt2img'}`")
        c1.markdown(f"**Model:** `{preview.get('local_model_id_or_path') or '-'}`")
        c1.markdown(f"**Sampler:** `{preview.get('sampler_name') or '-'} / {preview.get('scheduler') or '-'}`")
        c2.markdown(f"**Size:** `{preview.get('width') or '-'} x {preview.get('height') or '-'}`")
        c2.markdown(f"**Steps / CFG:** `{preview.get('steps') or '-'} / {preview.get('cfg') or '-'}`")
        c2.markdown(f"**Seed:** `{preview.get('seed') if preview.get('seed') is not None else '-'}`")
        pos = str(preview.get('positive_prompt') or '').strip()
        neg = str(preview.get('negative_prompt') or '').strip()
        if pos:
            st.text_area('Positive prompt (parsed)', value=pos, height=100, disabled=True, key=f'{key_prefix}_parsed_positive')
        if neg:
            st.text_area('Negative prompt (parsed)', value=neg, height=80, disabled=True, key=f'{key_prefix}_parsed_negative')
        unsupported = preview.get('unsupported_class_names') or []
        ignored = preview.get('ignored_class_names') or []
        badge_cols = st.columns(3)
        badge_cols[0].caption(f"Supported summary nodes: {len(preview.get('node_summary') or [])}")
        badge_cols[1].caption(f"Unsupported nodes: {len(unsupported)}")
        badge_cols[2].caption(f"Ignored nodes: {len(ignored)}")
        sections: list[DiagnosticsSection] = []
        if unsupported:
            sections.append(DiagnosticsSection(
                label="Unsupported workflow nodes",
                payload={"unsupported_class_names": unsupported, "unsupported_nodes": preview.get('unsupported_nodes') or []},
                message="Image: the workflow contains unsupported nodes; the app will ignore them or only parse part of the graph.",
                level="warning",
            ))
        if ignored:
            sections.append(DiagnosticsSection(
                label="Ignored workflow nodes",
                payload={"ignored_class_names": ignored, "ignored_nodes": preview.get('ignored_nodes') or []},
                message="Image: the workflow contains ignored nodes in the local parser preview.",
                level="info",
            ))
        meta = {
            'workflow_path': preview.get('workflow_path') or '',
            'node_count': preview.get('node_count') or 0,
            'checkpoints': preview.get('checkpoints') or [],
            'controlnet_models': preview.get('controlnet_models') or [],
            'image_inputs': preview.get('image_inputs') or [],
            'mask_inputs': preview.get('mask_inputs') or [],
            'loras': preview.get('loras') or [],
            'vae': preview.get('vae') or [],
        }
        sections.append(DiagnosticsSection(label="Workflow metadata", payload=meta))
        render_diagnostics_sections(sections)
        apply_cols = st.columns([1, 2])
        if apply_cols[0].button('Apply parsed values to current preset', key=f'{key_prefix}_apply_parsed', width="stretch"):
            applied = _apply_parsed_values_to_current_preset(preview)
            if applied:
                _image_provider_message('success', f"Image: applied parsed values into the current preset ({len(applied)} field(s)).")
            else:
                _image_provider_message("warning", "Image: there is no parsed value that can be applied to the current preset.")
            safe_rerun()
        apply_cols[1].caption("Apply size / sampler / mode / model and related inputs from the parsed workflow result into the current UI.")
        st.caption('Node summary')
        render_json_summary_expander("Node summary details", preview.get('node_summary') or [], expanded=False)

def _render_image_provider_message() -> None:
    render_action_status("image_provider_message")


def _handle_image_provider_actions(provider: str, settings: dict[str, Any]) -> None:
    provider_meta = get_sd_provider(provider)

    def _refresh() -> None:
        if provider_meta.uses_diffusers_runtime:
            status = local_provider_status(settings)
            models = status.get("local_models") or []
            model_count = status.get("model_count", len(models))
            set_action_status("image_provider_message", "success", f"Image: scanned {status.get('models_dir') or '-'} and found {model_count} local model(s).")
        elif provider_meta.is_comfyui and provider_meta.is_local:
            set_action_status("image_provider_message", "success", "Image: refreshed local ComfyUI workflow settings.")
        elif provider_meta.requires_base_url:
            base_url = str(settings.get("base_url") or "").strip() or "the configured endpoint"
            set_action_status("image_provider_message", "success", f"Image: refreshed provider config from {base_url}.")
        else:
            set_action_status("image_provider_message", "success", f"Image: refreshed provider config for {provider}.")

    def _test() -> None:
        validation_error = _validate_provider_before_test(provider, settings)
        if validation_error:
            set_action_status("image_provider_message", "warning", validation_error)
            return

        try:
            if provider_meta.is_local:
                logs = preload_local_provider({**settings, "local_allow_network": False})
                set_action_status(
                    "image_provider_message",
                    "success",
                    f"Image: test {provider} succeeded.",
                )
            else:
                base_url = str(settings.get("base_url") or "").strip()
                if not base_url:
                    raise ValueError("Base URL is empty.")
                import requests
                response = requests.get(base_url.rstrip('/'), timeout=10)
                set_action_status(
                    "image_provider_message",
                    "success",
                    f"Image: test {provider} OK | HTTP {response.status_code} | {base_url}",
                )
        except Exception as exc:
            details = f"{exc.__class__.__name__}: {exc}"

            if provider_meta.missing_model_requires_warning and "local_model_id_or_path" in str(exc):
                set_action_status(
                    "image_provider_message",
                    "warning",
                    _friendly_local_sd_missing_model_message(),
                )
                return

            if provider_meta.uses_diffusers_runtime:
                set_action_status(
                    "image_provider_message",
                    "error",
                    (
                        "Could not test Stable Diffusion local right now. "
                        "Check the model, device/dtype, and local runtime, then try again. "
                        f"Details: {details}"
                    ),
                )
                return

            if provider_meta.is_comfyui and provider_meta.is_local:
                set_action_status(
                    "image_provider_message",
                    "error",
                    (
                        "Could not test ComfyUI local right now. "
                        "Check the workflow, local model, and ComfyUI runtime, then try again. "
                        f"Details: {details}"
                    ),
                )
                return

            set_action_status(
                "image_provider_message",
                "error",
                (
                    f"Could not test provider {provider} right now. "
                    "Check the URL, API key, and connection config, then try again. "
                    f"Details: {details}"
                ),
            )

    def _update() -> None:
        try:
            model_ref = str(settings.get("local_model_id_or_path") or "").strip()
            if provider_meta.uses_diffusers_runtime and model_ref.lower().endswith((".safetensors", ".ckpt")):
                set_action_status(
                    "image_provider_message",
                    "warning",
                    "Image: single-file local checkpoint does not require Update. Use Test/Run with Local model id / path instead."
                )
                return

            if provider_meta.is_local:
                logs = preload_local_provider({**settings, "local_allow_network": True})
                target_dir = provider_target_dir("image", provider_meta.model_scan_provider_id, __file__)
                set_action_status("image_provider_message", "success", f"Image: updated/downloaded model assets into {target_dir}.")
            else:
                set_action_status("image_provider_message", "success", f"Image: provider {provider} uses an external endpoint; Update only refreshes the current connection from the configured URL.")
        except Exception as exc:
            set_action_status("image_provider_message", "error", f"Image: update {provider} failed ({exc.__class__.__name__}: {exc})")

    render_provider_action_row([
        ProviderAction("refresh", "Refresh", key=f"image_provider_refresh::{provider}", callback=_refresh),
        ProviderAction("test", "Test", key=f"image_provider_test::{provider}", callback=_test),
        ProviderAction("update", "Update", key=f"image_provider_update::{provider}", callback=_update),
    ])

def get_image_settings() -> dict[str, Any]:
    with st.sidebar:
        st.header(SidebarSection.PROVIDER)
        provider_options = list_sd_provider_ids()
        provider_labels = get_sd_provider_choices()
        current_provider = str(st.session_state.get("image_provider") or "stable_diffusion_local")
        provider = st.selectbox(
            "SD Provider",
            options=provider_options,
            index=_index_or_zero(provider_options, current_provider),
            format_func=lambda provider_id: provider_labels.get(str(provider_id), str(provider_id)),
        )
        provider_meta = get_sd_provider(provider)
        st.session_state["image_provider"] = provider

        uses_http = provider_meta.requires_base_url
        default_url = provider_meta.default_base_url
        if uses_http:
            base_url = st.text_input("Base URL", value=str(st.session_state.get("image_base_url") or default_url))
            if provider_meta.uses_api_key:
                api_key = st.text_input("API key", value=str(st.session_state.get("image_api_key") or ""), type="password")
            else:
                api_key = ""
        else:
            base_url = ""
            api_key = ""
            if provider_meta.local_caption:
                st.caption(provider_meta.local_caption)

        action_settings = {
            "provider": provider,
            "base_url": base_url,
            "api_key": api_key,
            "local_model_id_or_path": str(st.session_state.get("image_local_model_id_or_path") or ""),
            "local_device": str(st.session_state.get("image_local_device") or "cuda"),
            "local_dtype": str(st.session_state.get("image_local_dtype") or "auto"),
            "local_variant": str(st.session_state.get("image_local_variant") or ""),
            "local_use_safetensors": bool(st.session_state.get("image_local_use_safetensors", True)),
            "local_enable_attention_slicing": bool(st.session_state.get("image_local_enable_attention_slicing", True)),
            "local_enable_model_cpu_offload": bool(st.session_state.get("image_local_enable_model_cpu_offload", False)),
            "workflow_json_file": str(st.session_state.get("image_workflow_json_file") or ""),
            "cover_workflow_json_file": str(st.session_state.get("image_cover_workflow_json_file") or ""),
            "scene_workflow_json_file": str(st.session_state.get("image_scene_workflow_json_file") or ""),
            "fallback_workflow_json_file": str(st.session_state.get("image_workflow_json_file") or ""),
            "auto_select_workflow_by_kind": bool(st.session_state.get("image_auto_select_workflow_by_kind", True)),
            "provider_payload": {
                "local_generation_mode": str(st.session_state.get("image_local_generation_mode") or "txt2img"),
                "local_pipeline_family": str(st.session_state.get("image_local_pipeline_family") or "sd15"),
                "local_original_config_file": str(st.session_state.get("image_local_original_config_file") or ""),
                "local_controlnet_model_id_or_path": str(st.session_state.get("image_local_controlnet_model_id_or_path") or ""),
                "local_disable_safety_checker": bool(st.session_state.get("image_local_disable_safety_checker", False)),
            },
        }
        _handle_image_provider_actions(provider, action_settings)
        _render_image_provider_message()
        if provider_meta.show_model_inventory:
            models_dir = provider_models_dir("image", __file__)
            local_models = list_local_models("image", __file__)
            st.caption(f"Models dir: {models_dir}")
            st.caption(f"Local models: {', '.join(local_models[:6]) if local_models else '-'}")
        _, advanced_provider_payload = _render_advanced_payload_json(provider_meta)

        st.header(SidebarSection.INPUTS_OUTPUTS)
        handoff_dir = st.text_input("Story handoff directory", value=str(st.session_state.get("image_handoff_dir") or ""))
        input_dir = st.text_input("Input directory", value=str(st.session_state.get("image_input_dir") or "image/prompt_bundle"))
        output_dir = st.text_input("Image output directory", value=str(st.session_state.get("image_output_dir") or "output"))

        st.header(SidebarSection.GENERATION)
        width = st.number_input("Width", min_value=256, max_value=4096, value=int(st.session_state.get("image_width") or 512), step=64)
        height = st.number_input("Height", min_value=256, max_value=4096, value=int(st.session_state.get("image_height") or 768), step=64)
        steps = st.number_input("Steps", min_value=1, max_value=150, value=int(st.session_state.get("image_steps") or 30), step=1)
        cfg = st.number_input("CFG", min_value=1.0, max_value=30.0, value=float(st.session_state.get("image_cfg") or 6.5), step=0.5)
        sampler_options = ["dpmpp_2m", "dpmpp_2m_karras", "euler", "euler_a", "unipc"]
        current_sampler_name = str(st.session_state.get("image_sampler_name") or "dpmpp_2m").strip()
        if current_sampler_name and current_sampler_name not in sampler_options:
            sampler_options = [current_sampler_name, *sampler_options]
        sampler_name = st.selectbox("Sampler name", options=sampler_options, index=_index_or_zero(sampler_options, current_sampler_name or "dpmpp_2m"))

        scheduler_options = ["karras", "default", "sgm_uniform", "exponential", "simple"]
        current_scheduler = str(st.session_state.get("image_scheduler") or "karras").strip()
        if current_scheduler and current_scheduler not in scheduler_options:
            scheduler_options = [current_scheduler, *scheduler_options]
        scheduler = st.selectbox("Scheduler", options=scheduler_options, index=_index_or_zero(scheduler_options, current_scheduler or "karras"))
        seed = st.number_input("Seed (-1 = random)", value=int(st.session_state.get("image_seed") or -1), step=1)
        st.caption("Negative prompt is edited in the Prompt tab; the sidebar no longer exposes this field.")

        local_model_id_or_path = str(st.session_state.get("image_local_model_id_or_path") or "")
        local_device = str(st.session_state.get("image_local_device") or "cuda")
        local_dtype = str(st.session_state.get("image_local_dtype") or "auto")
        local_variant = str(st.session_state.get("image_local_variant") or "")
        local_use_safetensors = bool(st.session_state.get("image_local_use_safetensors", True))
        local_enable_attention_slicing = bool(st.session_state.get("image_local_enable_attention_slicing", True))
        local_enable_model_cpu_offload = bool(st.session_state.get("image_local_enable_model_cpu_offload", False))
        local_preload_model_on_startup = bool(st.session_state.get("image_local_preload_model_on_startup", False))
        local_disable_safety_checker = bool(st.session_state.get("image_local_disable_safety_checker", False))
        local_auto_shorten_prompt = bool(st.session_state.get("image_local_auto_shorten_prompt", False))
        local_auto_shorten_negative_prompt = bool(st.session_state.get("image_local_auto_shorten_negative_prompt", False))
        local_generation_mode = str(st.session_state.get("image_local_generation_mode") or "txt2img")
        local_pipeline_family = str(st.session_state.get("image_local_pipeline_family") or "sd15")
        local_original_config_file = str(st.session_state.get("image_local_original_config_file") or "")
        local_diffusers_config_repo = str(st.session_state.get("image_local_diffusers_config_repo") or "")
        local_init_image = str(st.session_state.get("image_local_init_image") or "")
        local_img2img_strength = float(st.session_state.get("image_local_img2img_strength") or 0.45)
        local_controlnet_model_id_or_path = str(st.session_state.get("image_local_controlnet_model_id_or_path") or "")
        local_control_image = str(st.session_state.get("image_local_control_image") or "")
        local_control_preprocessor = str(st.session_state.get("image_local_control_preprocessor") or "none")
        local_controlnet_conditioning_scale = float(st.session_state.get("image_local_controlnet_conditioning_scale") or 1.0)
        local_inpaint_image = str(st.session_state.get("image_local_inpaint_image") or "")
        local_inpaint_mask = str(st.session_state.get("image_local_inpaint_mask") or "")
        local_inpaint_strength = float(st.session_state.get("image_local_inpaint_strength") or 0.55)
        local_resolve_bundle_assets = bool(st.session_state.get("image_local_resolve_bundle_assets", True))
        local_adetailer_enabled = bool(st.session_state.get("image_local_adetailer_enabled", True))
        local_adetailer_detector = str(st.session_state.get("image_local_adetailer_detector") or "cascade_combo")
        local_adetailer_prompt = str(st.session_state.get("image_local_adetailer_prompt") or "")
        local_adetailer_negative_prompt = str(st.session_state.get("image_local_adetailer_negative_prompt") or "")
        local_adetailer_strength = float(st.session_state.get("image_local_adetailer_strength") or 0.3)
        local_adetailer_steps = int(st.session_state.get("image_local_adetailer_steps") or 15)
        local_adetailer_padding = float(st.session_state.get("image_local_adetailer_padding") or 0.35)
        local_adetailer_max_detections = int(st.session_state.get("image_local_adetailer_max_detections") or 4)
        local_adetailer_regions = str(st.session_state.get("image_local_adetailer_regions") or "")
        local_adetailer_yolo_model = str(st.session_state.get("image_local_adetailer_yolo_model") or "")
        local_adetailer_yolo_confidence = float(st.session_state.get("image_local_adetailer_yolo_confidence") or 0.25)
        local_lora_enabled = bool(st.session_state.get("image_local_lora_enabled", False))
        local_lora_model_id_or_path = str(st.session_state.get("image_local_lora_model_id_or_path") or "")
        local_lora_scale = float(st.session_state.get("image_local_lora_scale") or 1.0)
        local_num_images_per_prompt = int(st.session_state.get("image_local_num_images_per_prompt") or 1)
        local_model_target_dir = str(provider_target_dir("image", provider_meta.model_scan_provider_id, __file__))
        local_controlnet_target_dir = str(provider_target_dir("image", "controlnet_local", __file__))
        local_lora_target_dir = str(provider_target_dir("image", "lora_local", __file__))
        negative_prompt = str(st.session_state.get("image_negative_prompt") or "")

        if provider_meta.supports_model_browser:
            st.header(SidebarSection.ADVANCED)
            st.subheader("Local detail pass")
            local_adetailer_enabled = st.checkbox(
                "Enable local ADetailer-like pass",
                value=local_adetailer_enabled,
                help="Refine detected regions with a local img2img pass after generation finishes.",
            )
            if local_adetailer_enabled:
                detector_options = ["mediapipe_face_person", "mediapipe_face", "yolo", "cascade_combo", "face_haar", "manual_regions"]
                local_adetailer_detector = st.selectbox(
                    "ADetailer detector",
                    options=detector_options,
                    index=_index_or_zero(detector_options, local_adetailer_detector),
                )
                local_adetailer_prompt = st.text_input("ADetailer prompt override", value=local_adetailer_prompt)
                local_adetailer_negative_prompt = st.text_input("ADetailer negative prompt override", value=local_adetailer_negative_prompt)
                local_adetailer_strength = st.slider("ADetailer strength", min_value=0.05, max_value=0.8, value=float(local_adetailer_strength), step=0.05)
                local_adetailer_steps = st.number_input("ADetailer steps", min_value=4, max_value=80, value=int(local_adetailer_steps), step=1)
                local_adetailer_padding = st.slider("ADetailer padding", min_value=0.0, max_value=1.0, value=float(local_adetailer_padding), step=0.05)
                local_adetailer_max_detections = st.number_input(
                    "ADetailer max detections",
                    min_value=1,
                    max_value=20,
                    value=int(local_adetailer_max_detections),
                    step=1,
                )
                if local_adetailer_detector == "yolo":
                    local_adetailer_yolo_model = st.text_input(
                        "YOLO model path / id",
                        value=local_adetailer_yolo_model,
                        help="Example: yolov8n.pt, yolov8n-face.pt, or a local path to a YOLO model.",
                    )
                    local_adetailer_yolo_confidence = st.slider(
                        "YOLO confidence",
                        min_value=0.05,
                        max_value=0.95,
                        value=float(local_adetailer_yolo_confidence),
                        step=0.05,
                    )
                if local_adetailer_detector == "manual_regions":
                    local_adetailer_regions = st.text_area(
                        "ADetailer manual regions (JSON)",
                        value=local_adetailer_regions,
                        height=120,
                        help="Example: [{\"x\":120,\"y\":80,\"w\":220,\"h\":220}]",
                    )

        if provider_meta.supports_model_browser:
            st.header(SidebarSection.RUNTIME)
            local_model_id_or_path, local_model_target_dir = _model_target_selector(
                label="Local model id / path",
                branch="image",
                provider_id=provider_meta.model_scan_provider_id,
                current_value=local_model_id_or_path,
                key_prefix="image_local_model",
                placeholder="runwayml/stable-diffusion-v1-5 or image/models/sdxl",
                suggested_default=provider_meta.default_model,
                help_text=(
                    "Enter a Hugging Face model id or a local path to a Stable Diffusion model. "
                    "Example: runwayml/stable-diffusion-v1-5, stabilityai/sdxl-turbo, or image/models/sdxl"
                ),
                preferred_suffixes=provider_meta.preferred_model_suffixes,
                prefer_first_match_as_default=provider_meta.prefer_first_model_as_default,
            )
            _render_target_path_tools(label="Model target path", path_value=local_model_target_dir, key_prefix="image_local_model")
            _render_model_type_hint(model_ref=local_model_id_or_path, mode=local_generation_mode, provider=provider, key_prefix="image_local_model")
            if provider_meta.missing_model_requires_warning and not str(local_model_id_or_path or "").strip():
                render_user_message(
                    UserMessage(
                        level="warning",
                        title="Local model is required",
                        body=(
                            "Stable Diffusion local requires **Local model id / path** before you click Test or Generate."
                        ),
                        actions=(
                            GuidanceAction(f"Use the default model quickly: `{_DEFAULT_LOCAL_SD_MODEL}`."),
                            GuidanceAction("Or choose a scanned local model under image/models/."),
                        ),
                    )
                )

            local_device_options = ["cuda", "prefer_gpu", "mps", "cpu"]
            local_dtype_options = ["auto", "float16", "bfloat16", "float32"]
            local_device = st.selectbox("Local device", options=local_device_options, index=_index_or_zero(local_device_options, local_device))
            local_dtype = st.selectbox("Local dtype", options=local_dtype_options, index=_index_or_zero(local_dtype_options, local_dtype))
            local_variant = st.text_input("Local variant", value=local_variant, help="Example: fp16 if the model repo exposes a dedicated variant.")
            local_use_safetensors = st.checkbox("Prefer safetensors", value=local_use_safetensors)
            local_enable_attention_slicing = st.checkbox("Enable attention slicing", value=local_enable_attention_slicing)
            local_enable_model_cpu_offload = st.checkbox("Enable model CPU offload", value=local_enable_model_cpu_offload)
            local_disable_safety_checker = st.checkbox(
                "Disable Diffusers safety checker",
                value=local_disable_safety_checker,
                help="Private/audit use only. Keep this off for public-facing generation.",
            )
            local_preload_model_on_startup = st.checkbox(
                "Preload local model on startup",
                value=local_preload_model_on_startup,
                help="Preload the pipeline so the first Generate run is not slowed down by a cold start.",
            )
            local_resolve_bundle_assets = st.checkbox(
                "Auto-resolve init/control/mask assets from bundle",
                value=local_resolve_bundle_assets,
                help="Prefer resolving images from the prompt bundle/manifest first, and only use manual paths when you need an override.",
            )
            if provider_meta.uses_diffusers_runtime:
                local_num_images_per_prompt = st.number_input(
                    "Images per prompt",
                    min_value=1,
                    max_value=8,
                    value=int(local_num_images_per_prompt),
                    step=1,
                    help="Generate multiple output variants for each prompt. Extra images are saved with _batchNN suffixes and shown in result galleries.",
                )

            if _provider_has(provider_meta, "lora"):
                st.header("LoRA")
                local_lora_enabled = st.checkbox(
                    "Enable LoRA",
                    value=local_lora_enabled,
                    help="Load one local LoRA adapter into the Diffusers pipeline after the base model is ready.",
                )
                if local_lora_enabled:
                    local_lora_model_id_or_path, local_lora_target_dir = _model_target_selector(
                        label="LoRA model id / path",
                        branch="image",
                        provider_id="lora_local",
                        current_value=local_lora_model_id_or_path,
                        key_prefix="image_local_lora_model",
                        placeholder="image/models/lora_local/style.safetensors",
                        help_text="Enter a local LoRA file/folder or a Hugging Face LoRA repo id.",
                        preferred_suffixes=(".safetensors", ".bin", ".pt"),
                        prefer_first_match_as_default=True,
                    )
                    _render_target_path_tools(label="LoRA target path", path_value=local_lora_target_dir, key_prefix="image_local_lora_model")
                    local_lora_scale = st.slider("LoRA scale", min_value=0.0, max_value=2.0, value=float(local_lora_scale), step=0.05)

            st.header("Generation mode")
            local_mode_options = ["txt2img", "img2img", "controlnet", "inpaint"]
            local_generation_mode = st.selectbox(
                "Mode",
                options=local_mode_options,
                index=_index_or_zero(local_mode_options, local_generation_mode),
            )
            local_pipeline_family = st.selectbox(
                "Single-file pipeline family",
                options=["sd15", "sdxl"],
                index=_index_or_zero(["sd15", "sdxl"], local_pipeline_family),
                help="Use this when Local model id / path is a .safetensors or .ckpt file. Diffusers repos/folders still use from_pretrained().",
            )
            local_original_config_file = _auto_original_config_for_family(local_pipeline_family)
            st.text_input(
                "Original config file (optional)",
                value=local_original_config_file,
                disabled=True,
                help="Auto-filled from the selected single-file pipeline family.",
            )
            local_diffusers_config_repo = st.text_input(
                "Diffusers config repo (optional)",
                value=local_diffusers_config_repo,
                help=(
                    "Optional local diffusers model repo folder for single-file checkpoints. "
                    "Leave empty if the auto-filled original config is enough."
                ),
            )

            model_path_lower = str(local_model_id_or_path or "").strip().lower()
            is_single_file_model = model_path_lower.endswith((".safetensors", ".ckpt"))
            resolved_original_config = _resolve_workspace_path(local_original_config_file) if str(local_original_config_file or "").strip() else None
            config_exists = bool(resolved_original_config and resolved_original_config.exists())
            if is_single_file_model and resolved_original_config is not None and not config_exists:
                render_user_message(
                    UserMessage(
                        level="warning",
                        title="Original config file not found",
                        body=(
                            "The **Original config file** path currently does not exist on this machine. "
                            "Check the path again, or use the suggested config that matches the pipeline family."
                        ),
                        actions=(
                            GuidanceAction(f"Current path: `{local_original_config_file}`"),
                            GuidanceAction("`sd15` -> `image/models/configs/v1-inference.yaml`"),
                            GuidanceAction("`sdxl` -> `image/models/configs/sdxl-base-inference.yaml`"),
                        ),
                    )
                )
            if local_generation_mode == "img2img":
                local_init_image = st.text_input(
                    "Init image path (optional)",
                    value=local_init_image,
                    help="May be left empty if the bundle/manifest already contains a suitable init image.",
                )
                local_img2img_strength = st.slider("Img2img strength", min_value=0.05, max_value=0.95, value=float(local_img2img_strength), step=0.05)
            elif local_generation_mode == "controlnet":
                local_controlnet_model_id_or_path, local_controlnet_target_dir = _model_target_selector(
                    label="ControlNet model id / path",
                    branch="image",
                    provider_id="controlnet_local",
                    current_value=local_controlnet_model_id_or_path,
                    key_prefix="image_local_controlnet_model",
                )
                _render_target_path_tools(label="ControlNet target path", path_value=local_controlnet_target_dir, key_prefix="image_local_controlnet_model")
                _render_model_type_hint(model_ref=local_controlnet_model_id_or_path, mode="controlnet", provider=provider, key_prefix="image_local_controlnet_model")
                local_control_image = st.text_input(
                    "Control image path (optional)",
                    value=local_control_image,
                    help="May be left empty if the bundle/manifest already contains a suitable control image.",
                )
                local_control_preprocessor = st.selectbox(
                    "Control preprocessor",
                    options=["none", "canny"],
                    index=_index_or_zero(["none", "canny"], local_control_preprocessor),
                )
                local_controlnet_conditioning_scale = st.slider(
                    "ControlNet conditioning scale",
                    min_value=0.1,
                    max_value=2.0,
                    value=float(local_controlnet_conditioning_scale),
                    step=0.1,
                )
            elif local_generation_mode == "inpaint":
                local_inpaint_image = st.text_input(
                    "Inpaint image path (optional)",
                    value=local_inpaint_image,
                    help="May be left empty if the bundle/manifest already contains an inpaint source image.",
                )
                local_inpaint_mask = st.text_input(
                    "Inpaint mask path (optional)",
                    value=local_inpaint_mask,
                    help="May be left empty if the bundle/manifest already contains the matching mask.",
                )
                local_inpaint_strength = st.slider(
                    "Inpaint strength",
                    min_value=0.05,
                    max_value=0.95,
                    value=float(local_inpaint_strength),
                    step=0.05,
                )
        else:
            st.session_state["image_local_preload_model_on_startup"] = local_preload_model_on_startup

        if _provider_has(provider_meta, "comfyui_routing"):
            st.header(SidebarSection.ADVANCED)
            st.subheader("ComfyUI routing")
            auto_select_workflow_by_kind = st.checkbox("Auto-select workflow by image kind", value=bool(st.session_state.get("image_auto_select_workflow_by_kind", True)))
            workflow_json_file = st.text_input("Fallback workflow JSON file", value=str(st.session_state.get("image_workflow_json_file") or default_comfyui_workflow_file()))
            cover_workflow_json_file = st.text_input("Cover workflow JSON file", value=str(st.session_state.get("image_cover_workflow_json_file") or ""))
            scene_workflow_json_file = st.text_input("Scene workflow JSON file", value=str(st.session_state.get("image_scene_workflow_json_file") or ""))
            positive_prompt_node_id = st.text_input("Positive prompt node id", value=str(st.session_state.get("image_positive_prompt_node_id") or "2"))
            negative_prompt_node_id = st.text_input("Negative prompt node id", value=str(st.session_state.get("image_negative_prompt_node_id") or "3"))
            sampler_node_id = st.text_input("Sampler node id", value=str(st.session_state.get("image_sampler_node_id") or "5"))
            latent_size_node_id = st.text_input("Latent size node id", value=str(st.session_state.get("image_latent_size_node_id") or "4"))
            output_node_ids = st.text_input("Output node ids", value=str(st.session_state.get("image_output_node_ids") or "7"))
            poll_interval = st.number_input("Poll interval (s)", min_value=0.2, max_value=30.0, value=float(st.session_state.get("image_poll_interval") or 1.5), step=0.1)
            max_wait_s = st.number_input("Max wait (s)", min_value=10, max_value=3600, value=int(st.session_state.get("image_max_wait_s") or 180), step=10)

            st.subheader("ComfyUI LoRA")
            local_lora_enabled = st.checkbox(
                "Enable LoRA",
                value=local_lora_enabled,
                help="Update existing LoRA loader nodes in the selected ComfyUI workflow before it is queued.",
            )
            if local_lora_enabled:
                if provider_meta.is_local:
                    local_lora_model_id_or_path, local_lora_target_dir = _model_target_selector(
                        label="LoRA model id / path",
                        branch="image",
                        provider_id="lora_local",
                        current_value=local_lora_model_id_or_path,
                        key_prefix="image_comfy_lora_model",
                        placeholder="image/models/lora_local/style.safetensors",
                        help_text="Enter a local LoRA file/folder or the LoRA name used by the workflow.",
                        preferred_suffixes=(".safetensors", ".bin", ".pt"),
                        prefer_first_match_as_default=True,
                    )
                    _render_target_path_tools(label="LoRA target path", path_value=local_lora_target_dir, key_prefix="image_comfy_lora_model")
                else:
                    local_lora_model_id_or_path = st.text_input(
                        "LoRA name / path",
                        value=local_lora_model_id_or_path,
                        help="Use the LoRA filename or subpath as the remote ComfyUI server sees it, for example style.safetensors.",
                    )
                local_lora_scale = st.slider("LoRA scale", min_value=0.0, max_value=2.0, value=float(local_lora_scale), step=0.05)

            if _provider_supports_comfyui_workflow_preview(provider_meta):
                _render_comfyui_workflow_preview(label="Fallback workflow", workflow_file=workflow_json_file, key_prefix="image_comfy_preview_fallback")
                if cover_workflow_json_file and cover_workflow_json_file != workflow_json_file:
                    _render_comfyui_workflow_preview(label="Cover workflow", workflow_file=cover_workflow_json_file, key_prefix="image_comfy_preview_cover")
                if scene_workflow_json_file and scene_workflow_json_file != workflow_json_file:
                    _render_comfyui_workflow_preview(label="Scene workflow", workflow_file=scene_workflow_json_file, key_prefix="image_comfy_preview_scene")
        else:
            auto_select_workflow_by_kind = bool(st.session_state.get("image_auto_select_workflow_by_kind", True))
            workflow_json_file = str(st.session_state.get("image_workflow_json_file") or "")
            cover_workflow_json_file = str(st.session_state.get("image_cover_workflow_json_file") or "")
            scene_workflow_json_file = str(st.session_state.get("image_scene_workflow_json_file") or "")
            positive_prompt_node_id = str(st.session_state.get("image_positive_prompt_node_id") or "2")
            negative_prompt_node_id = str(st.session_state.get("image_negative_prompt_node_id") or "3")
            sampler_node_id = str(st.session_state.get("image_sampler_node_id") or "5")
            latent_size_node_id = str(st.session_state.get("image_latent_size_node_id") or "4")
            output_node_ids = str(st.session_state.get("image_output_node_ids") or "7")
            poll_interval = float(st.session_state.get("image_poll_interval") or 1.5)
            max_wait_s = int(st.session_state.get("image_max_wait_s") or 180)

    st.session_state["image_base_url"] = base_url
    st.session_state["image_api_key"] = api_key
    st.session_state["image_handoff_dir"] = handoff_dir
    st.session_state["image_input_dir"] = input_dir
    st.session_state["image_output_dir"] = output_dir
    st.session_state["image_width"] = int(width)
    st.session_state["image_height"] = int(height)
    st.session_state["image_steps"] = int(steps)
    st.session_state["image_cfg"] = float(cfg)
    st.session_state["image_sampler_name"] = sampler_name
    st.session_state["image_scheduler"] = scheduler
    st.session_state["image_seed"] = int(seed)
    st.session_state["image_negative_prompt"] = negative_prompt
    st.session_state["image_local_model_id_or_path"] = local_model_id_or_path
    st.session_state["image_local_device"] = local_device
    st.session_state["image_local_dtype"] = local_dtype
    st.session_state["image_local_variant"] = local_variant
    st.session_state["image_local_use_safetensors"] = bool(local_use_safetensors)
    st.session_state["image_local_enable_attention_slicing"] = bool(local_enable_attention_slicing)
    st.session_state["image_local_enable_model_cpu_offload"] = bool(local_enable_model_cpu_offload)
    st.session_state["image_local_preload_model_on_startup"] = bool(local_preload_model_on_startup)
    st.session_state["image_local_disable_safety_checker"] = bool(local_disable_safety_checker)
    st.session_state["image_local_auto_shorten_prompt"] = bool(local_auto_shorten_prompt)
    st.session_state["image_local_auto_shorten_negative_prompt"] = bool(local_auto_shorten_negative_prompt)
    st.session_state["image_local_generation_mode"] = local_generation_mode
    st.session_state["image_local_pipeline_family"] = local_pipeline_family
    st.session_state["image_local_original_config_file"] = local_original_config_file
    st.session_state["image_local_diffusers_config_repo"] = local_diffusers_config_repo
    st.session_state["image_local_init_image"] = local_init_image
    st.session_state["image_local_img2img_strength"] = float(local_img2img_strength)
    st.session_state["image_local_controlnet_model_id_or_path"] = local_controlnet_model_id_or_path
    st.session_state["image_local_control_image"] = local_control_image
    st.session_state["image_local_control_preprocessor"] = local_control_preprocessor
    st.session_state["image_local_controlnet_conditioning_scale"] = float(local_controlnet_conditioning_scale)
    st.session_state["image_local_inpaint_image"] = local_inpaint_image
    st.session_state["image_local_inpaint_mask"] = local_inpaint_mask
    st.session_state["image_local_inpaint_strength"] = float(local_inpaint_strength)
    st.session_state["image_local_resolve_bundle_assets"] = bool(local_resolve_bundle_assets)
    st.session_state["image_local_adetailer_enabled"] = bool(local_adetailer_enabled)
    st.session_state["image_local_adetailer_detector"] = local_adetailer_detector
    st.session_state["image_local_adetailer_prompt"] = local_adetailer_prompt
    st.session_state["image_local_adetailer_negative_prompt"] = local_adetailer_negative_prompt
    st.session_state["image_local_adetailer_strength"] = float(local_adetailer_strength)
    st.session_state["image_local_adetailer_steps"] = int(local_adetailer_steps)
    st.session_state["image_local_adetailer_padding"] = float(local_adetailer_padding)
    st.session_state["image_local_adetailer_max_detections"] = int(local_adetailer_max_detections)
    st.session_state["image_local_adetailer_regions"] = local_adetailer_regions
    st.session_state["image_local_adetailer_yolo_model"] = local_adetailer_yolo_model
    st.session_state["image_local_adetailer_yolo_confidence"] = float(local_adetailer_yolo_confidence)
    st.session_state["image_local_lora_enabled"] = bool(local_lora_enabled)
    st.session_state["image_local_lora_model_id_or_path"] = local_lora_model_id_or_path
    st.session_state["image_local_lora_scale"] = float(local_lora_scale)
    st.session_state["image_local_num_images_per_prompt"] = int(local_num_images_per_prompt)
    st.session_state["image_auto_select_workflow_by_kind"] = auto_select_workflow_by_kind
    st.session_state["image_workflow_json_file"] = workflow_json_file
    st.session_state["image_cover_workflow_json_file"] = cover_workflow_json_file
    st.session_state["image_scene_workflow_json_file"] = scene_workflow_json_file
    st.session_state["image_positive_prompt_node_id"] = positive_prompt_node_id
    st.session_state["image_negative_prompt_node_id"] = negative_prompt_node_id
    st.session_state["image_sampler_node_id"] = sampler_node_id
    st.session_state["image_latent_size_node_id"] = latent_size_node_id
    st.session_state["image_output_node_ids"] = output_node_ids
    st.session_state["image_poll_interval"] = float(poll_interval)
    st.session_state["image_max_wait_s"] = int(max_wait_s)

    provider_payload = {
        "local_generation_mode": local_generation_mode,
        "local_pipeline_family": local_pipeline_family,
        "local_original_config_file": local_original_config_file,
        "local_diffusers_config_repo": local_diffusers_config_repo,
        "local_init_image": local_init_image,
        "local_img2img_strength": float(local_img2img_strength),
        "local_controlnet_model_id_or_path": local_controlnet_model_id_or_path,
        "local_controlnet_target_dir": local_controlnet_target_dir,
        "local_control_image": local_control_image,
        "local_control_preprocessor": local_control_preprocessor,
        "local_controlnet_conditioning_scale": float(local_controlnet_conditioning_scale),
        "local_disable_safety_checker": bool(local_disable_safety_checker),
        "local_inpaint_image": local_inpaint_image,
        "local_inpaint_mask": local_inpaint_mask,
        "local_inpaint_strength": float(local_inpaint_strength),
        "local_resolve_bundle_assets": bool(local_resolve_bundle_assets),
        "local_adetailer_enabled": bool(local_adetailer_enabled),
        "local_adetailer_detector": local_adetailer_detector,
        "local_adetailer_prompt": local_adetailer_prompt,
        "local_adetailer_negative_prompt": local_adetailer_negative_prompt,
        "local_adetailer_strength": float(local_adetailer_strength),
        "local_adetailer_steps": int(local_adetailer_steps),
        "local_adetailer_padding": float(local_adetailer_padding),
        "local_adetailer_max_detections": int(local_adetailer_max_detections),
        "local_adetailer_regions": local_adetailer_regions,
        "local_adetailer_yolo_model": local_adetailer_yolo_model,
        "local_adetailer_yolo_confidence": float(local_adetailer_yolo_confidence),
        "local_lora_enabled": bool(local_lora_enabled),
        "local_lora_model_id_or_path": local_lora_model_id_or_path,
        "local_lora_target_dir": local_lora_target_dir,
        "local_lora_scale": float(local_lora_scale),
    }
    if provider_meta.uses_diffusers_runtime:
        provider_payload["num_images_per_prompt"] = int(local_num_images_per_prompt)
    provider_payload.update(advanced_provider_payload)
    return {
        "provider": provider,
        "base_url": base_url,
        "api_key": api_key,
        "handoff_dir": handoff_dir,
        "input_dir": input_dir,
        "output_dir": output_dir,
        "width": int(width),
        "height": int(height),
        "steps": int(steps),
        "cfg": float(cfg),
        "sampler_name": sampler_name,
        "scheduler": scheduler,
        "seed": int(seed),
        "negative_prompt": negative_prompt,
        "local_model_id_or_path": local_model_id_or_path,
        "local_model_target_dir": local_model_target_dir,
        "local_lora_target_dir": local_lora_target_dir,
        "local_original_config_file": local_original_config_file,
        "local_diffusers_config_repo": local_diffusers_config_repo,
        "local_device": local_device,
        "local_dtype": local_dtype,
        "local_variant": local_variant,
        "local_use_safetensors": bool(local_use_safetensors),
        "local_enable_attention_slicing": bool(local_enable_attention_slicing),
        "local_enable_model_cpu_offload": bool(local_enable_model_cpu_offload),
        "local_preload_model_on_startup": bool(local_preload_model_on_startup),
        "local_auto_shorten_prompt": bool(local_auto_shorten_prompt),
        "local_auto_shorten_negative_prompt": bool(local_auto_shorten_negative_prompt),
        "auto_select_workflow_by_kind": auto_select_workflow_by_kind,
        "workflow_json_file": workflow_json_file,
        "cover_workflow_json_file": cover_workflow_json_file,
        "scene_workflow_json_file": scene_workflow_json_file,
        "fallback_workflow_json_file": workflow_json_file,
        "positive_prompt_node_id": positive_prompt_node_id,
        "negative_prompt_node_id": negative_prompt_node_id,
        "sampler_node_id": sampler_node_id,
        "latent_size_node_id": latent_size_node_id,
        "output_node_ids": output_node_ids,
        "poll_interval": float(poll_interval),
        "max_wait_s": int(max_wait_s),
        "provider_payload": provider_payload,
    }


def render_settings_sidebar() -> dict[str, Any]:
    return get_image_settings()


def get_settings() -> dict[str, Any]:
    return get_image_settings()


def render_settings() -> dict[str, Any]:
    return get_image_settings()


def render_sidebar() -> dict[str, Any]:
    return render_settings_sidebar()

