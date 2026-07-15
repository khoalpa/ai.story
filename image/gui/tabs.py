from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
import streamlit as st

from image.gui.diagnostics_blocks import render_runtime_diagnostics_block
from image.gui.history_utils import append_deduped_tail_history_entry
from image.gui.progress_details import format_progress_text
from image.gui.runtime_usage import render_runtime_usage_compact
from image.gui.shared_state import (
    append_global_run_event,
    set_image_handoff,
    update_global_run_monitor,
)
from image.gui.user_messages import (
    show_empty_result,
    show_path_warning,
    show_preview_warning,
)
from image.gui.workspace_handoff import workspace_handoff_state
from image.gui.workspace_source_outputs import workspace_source_outputs

from image.app_api import RenderImageRequest
from image.gui.common_ui import _normalize_exc, _ui_error, _ui_info, _ui_success, _ui_warning
from image.gui.detector_ui import _render_adetailer_preview_for_entry
from image.gui.inpaint_utils import (
    _canvas_auto_load_key,
    _canvas_image_to_mask,
    _canvas_json_key,
    _canvas_mode_key,
    _canvas_rev_key,
    _canvas_seed_state,
    _clear_uploaded_inpaint_source,
    _clear_canvas,
    _collect_inpaint_source_candidates,
    _ensure_streamlit_canvas_compat,
    _hex_to_rgb,
    _has_uploaded_inpaint_source,
    _get_uploaded_inpaint_source_metadata,
    _can_apply_manual_inpaint_source,
    _inpaint_preview_source_caption,
    _inpaint_preview_source_badge_text,
    _inpaint_manual_source_key,
    _inpaint_source_upload_widget_key,
    _inpaint_uploaded_source_key,
    _inpaint_uploaded_source_clear_key,
    _is_uploaded_inpaint_preview_source,
    _inpaint_source_status_badge_text,
    _load_saved_mask_into_editor,
    _preview_sheet_export_path,
    _push_canvas_history,
    _resolve_inpaint_source_for_entry,
    _store_uploaded_inpaint_source,
    _set_canvas_state,
    _sync_inpaint_selection_to_settings,
    _undo_canvas,
    _render_detector_preview,
)
from image.gui.prompt_state import (
    _collect_prompt_override_payload,
    _ensure_prompt_edit_state,
    _format_provider_payload_json,
    _get_effective_prompt_edit,
    _parse_provider_payload_json,
    _reset_prompt_edit_state,
    _store_prompt_edit_state,
)
from image.gui.prompt_ui import _render_clip_token_estimate, _render_image_focus_hint, _render_prompt_autoshorten_status, _render_prompt_autoshorten_toggle, _render_prompt_trim_preview_block, _render_prompt_trim_status, _render_quick_input_previews
from image.gui.result_ui import _build_existing_run_preview_result, _list_image_files, _render_prompt_cards_in_run, _render_result_preview_panel
from image.gui.service import iter_prompt_files, run_image_job
from image.gui.state import IMAGE_INPAINT_MASK_PATH_KEY, IMAGE_INPAINT_SOURCE_PATH_KEY, IMAGE_RUN_HISTORY_KEY, ensure_session_defaults
from image.provider_runtime import (
    local_provider_status,
    build_debug_preview_sheet,
    overlay_mask_preview,
)
from image.runtime import package_root
from image.workflow_routing import infer_prompt_kind


def _resolve_workspace_path(path_value: str) -> Path:
    path = Path(str(path_value or "").strip()).expanduser()
    if path.is_absolute():
        return path
    return (package_root(__file__).parent / path).resolve()


def _prefill_from_story_handoff() -> None:
    incoming = workspace_handoff_state(st.session_state).story_image_handoff_dir
    if incoming and st.session_state.get("image_lock_to_story_handoff", True):
        st.session_state["image_handoff_dir"] = incoming
        if not str(st.session_state.get("image_output_dir") or "").strip():
            st.session_state["image_output_dir"] = str(Path(incoming) / "generated")
def _resolve_prompt_dir(settings: dict[str, Any]) -> Path | None:
    source_kind = str(st.session_state.get("image_source_kind") or "handoff").strip().lower()
    if source_kind == "handoff":
        base_dir = str(settings.get("handoff_dir") or st.session_state.get("image_handoff_dir") or "").strip()
    else:
        base_dir = str(settings.get("input_dir") or st.session_state.get("image_input_dir") or "").strip()
    if not base_dir:
        return None
    return _resolve_workspace_path(base_dir)
def _resolve_input_prompt_dir(settings: dict[str, Any]) -> Path | None:
    base_dir = str(settings.get("input_dir") or st.session_state.get("image_input_dir") or "").strip()
    if not base_dir:
        return None
    return _resolve_workspace_path(base_dir)
def _load_prompt_entries(prompt_dir: Path | None) -> list[dict[str, Any]]:
    if prompt_dir is None or not prompt_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for prompt_path, prompt_data, suggested_output in iter_prompt_files(prompt_dir):
        rel_path = str(prompt_path.relative_to(prompt_dir)).replace('\\', '/')
        entries.append({
            'path': prompt_path,
            'rel_path': rel_path,
            'kind': infer_prompt_kind(prompt_data, prompt_path),
            'slot': str(prompt_data.get('slot') or prompt_data.get('image_key') or prompt_path.stem),
            'prompt_data': prompt_data,
            'suggested_output': suggested_output,
        })
    return entries
def _resolve_test_prompt_bundle(settings: dict[str, Any]) -> tuple[Path | None, list[dict[str, Any]], list[str]]:
    _prefill_from_story_handoff()
    prompt_dir = _resolve_prompt_dir(settings)
    issues: list[str] = []
    if prompt_dir is None:
        source_kind = str(st.session_state.get("image_source_kind") or "handoff").strip().lower()
        if source_kind == "handoff":
            input_dir = _resolve_input_prompt_dir(settings)
            input_entries = _load_prompt_entries(input_dir)
            if input_entries:
                st.session_state["image_source_kind"] = "input"
                st.session_state["image_test_prompt_dir"] = str(input_dir)
                st.session_state["image_test_prompt_bundle"] = input_entries
                return input_dir, input_entries, issues
            issues.append(
                "Prompt source is set to handoff, but no Story handoff directory is available. "
                "Run Story and click Send to Image, or switch Prompt source to input and choose a prompt folder."
            )
        else:
            issues.append("Prompt source = input but the Input directory is not configured yet.")
        return None, [], issues
    if not prompt_dir.exists():
        issues.append(f"Prompt directory does not exist: {prompt_dir}")
        return prompt_dir, [], issues
    if not prompt_dir.is_dir():
        issues.append(f"Prompt directory is invalid (not a folder): {prompt_dir}")
        return prompt_dir, [], issues
    entries = _load_prompt_entries(prompt_dir)
    if entries:
        st.session_state["image_test_prompt_dir"] = str(prompt_dir)
        st.session_state["image_test_prompt_bundle"] = entries
        return prompt_dir, entries, issues
    manifest_path = prompt_dir / "manifest.json"
    if manifest_path.is_file():
        issues.append(
            "Prompt directory exists but no valid prompt file was found. "
            "Expected cover_prompt.json, scene_prompt.json, *_prompt.json, or scene_prompts/*.json."
        )
    else:
        issues.append(
            "Prompt directory exists but does not contain a valid prompt bundle, and manifest.json was not found either."
        )
    return prompt_dir, [], issues
def render_inpaint_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    _prefill_from_story_handoff()
    st.subheader("Inpaint mask editor")
    if str(settings.get("provider") or "") != "stable_diffusion_local":
        _ui_info("The mask editor currently supports stable_diffusion_local only.")
        return
    provider_payload = dict(settings.get("provider_payload") or {})
    if str(provider_payload.get("local_generation_mode") or "") != "inpaint":
        _ui_info("Switch Local generation mode to 'inpaint' to use the mask editor.")
        return
    prompt_dir, entries, issues = _resolve_test_prompt_bundle(settings)
    for issue in issues:
        _ui_warning(issue)
    if not entries:
        _ui_info("No valid prompt bundle is available to build the mask.")
        return
    _ensure_streamlit_canvas_compat()
    try:
        from streamlit_drawable_canvas import st_canvas  # type: ignore
    except Exception:
        _ui_warning("Missing streamlit-drawable-canvas. Install it with: pip install streamlit-drawable-canvas")
        return
    selected_rel_path = st.selectbox(
        "Choose prompt for inpaint",
        options=[entry["rel_path"] for entry in entries],
        format_func=lambda value: next((f"{entry['slot']} ({entry['rel_path']})" for entry in entries if entry['rel_path'] == value), value),
        key="image_inpaint_selected_prompt",
    )
    selected = next(entry for entry in entries if entry["rel_path"] == selected_rel_path)
    source_path, source_label = _resolve_inpaint_source_for_entry(settings, prompt_dir, selected)
    source_candidates = _collect_inpaint_source_candidates(settings, prompt_dir, selected)
    manual_source_key = _inpaint_manual_source_key(selected_rel_path)
    image_key = str((selected.get("prompt_data") or {}).get("image_key") or Path(selected_rel_path).stem).strip() or Path(selected_rel_path).stem
    mask_dir = (prompt_dir or Path.cwd()) / "scene_masks"
    mask_dir.mkdir(parents=True, exist_ok=True)
    mask_path = mask_dir / f"{image_key}.png"
    upload_key = _inpaint_source_upload_widget_key(selected_rel_path)
    uploaded_file = None
    uploaded_source_path = _inpaint_uploaded_source_key(selected_rel_path)
    clear_uploaded_key = _inpaint_uploaded_source_clear_key(selected_rel_path)
    uploaded_source_path_value, uploaded_source_label = _get_uploaded_inpaint_source_metadata(selected_rel_path)
    uploaded_source = None
    with st.expander("Available source images", expanded=not bool(source_path and source_path.is_file())):
        upload_col, clear_col, status_col, refresh_col, hint_col = st.columns([1.0, 0.85, 1.15, 0.75, 1.1])
        with upload_col:
            uploaded_file = st.file_uploader(
                "Upload source image",
                type=["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"],
                key=upload_key,
                help="Upload a local image to use as the inpaint source when the bundle does not provide one.",
            )
        with clear_col:
            if st.button("Clear uploaded source", key=clear_uploaded_key, width="stretch", disabled=not bool(st.session_state.get(uploaded_source_path) or uploaded_file is not None)):
                _clear_uploaded_inpaint_source(selected_rel_path=selected_rel_path)
                st.rerun()
        with refresh_col:
            if st.button("Refresh sources", key=f"refresh_sources::{selected_rel_path}", width="stretch"):
                st.rerun()
        with hint_col:
            st.caption("Re-scan after a run if new source files appeared.")
        if uploaded_file is not None:
            uploaded_source = _store_uploaded_inpaint_source(uploaded_file, prompt_dir=prompt_dir, selected_rel_path=selected_rel_path)
            st.session_state[uploaded_source_path] = str(uploaded_source)
            uploaded_source_path_value = uploaded_source
            uploaded_source_label = f"Uploaded source | {uploaded_source.name}"
            source_path = uploaded_source
            source_label = uploaded_source_label
            st.caption(f"Using uploaded source: {source_label}")
        elif uploaded_source_path_value is not None:
            source_path = uploaded_source_path_value
            source_label = uploaded_source_label
            st.caption(f"Using uploaded source: {source_label}")
        elif source_path is not None and source_path.is_file():
            st.caption(f"Using resolved source: {source_label}")
        else:
            st.caption("Upload an image or pick one of the available source files below.")
        if source_candidates:
            source_options = [str(path) for _, path in source_candidates]
            if uploaded_source_path_value is not None and str(uploaded_source_path_value) in source_options:
                default_source = str(uploaded_source_path_value)
            elif uploaded_source is not None and str(uploaded_source) in source_options:
                default_source = str(uploaded_source)
            else:
                default_source = str(st.session_state.get(manual_source_key) or source_options[0])
            if default_source not in source_options:
                default_source = source_options[0]
            selected_source_value = st.selectbox(
                "Choose source image",
                options=source_options,
                index=source_options.index(default_source),
                format_func=lambda value: next((f"{label} | {Path(value).name}" for label, path in source_candidates if str(path) == value), value),
                key=manual_source_key,
            )
            if _can_apply_manual_inpaint_source(uploaded_source_path_value=uploaded_source_path_value, uploaded_source=uploaded_source):
                source_path = Path(selected_source_value)
                source_label = next((f"{label} | {path}" for label, path in source_candidates if str(path) == selected_source_value), selected_source_value)
                st.caption(f"Using selected source: {source_label}")
        elif uploaded_source_path_value is None:
            _ui_warning("No fallback source images are available for this prompt. Upload one to continue.")
    if source_path is None or not source_path.is_file():
        _ui_warning("Could not auto-resolve the inpaint source image from the current bundle/path.")
        if uploaded_source_path_value is None and not source_candidates:
            return
    uploaded_source_active = _is_uploaded_inpaint_preview_source(source_path=source_path, uploaded_source_path_value=uploaded_source_path_value)
    with status_col:
        badge_text = _inpaint_source_status_badge_text(uploaded_source_active=uploaded_source_active)
        if uploaded_source_active:
            st.markdown(
                f"<span style='display:inline-block;padding:0.18rem 0.55rem;border-radius:999px;"
                f"background:#dbeafe;color:#1e3a8a;font-size:0.78rem;font-weight:700;"
                f"line-height:1.1'>{badge_text}</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<span style='display:inline-block;padding:0.18rem 0.55rem;border-radius:999px;"
                f"background:#ecfeff;color:#155e75;font-size:0.78rem;font-weight:700;"
                f"line-height:1.1'>{badge_text}</span>",
                unsafe_allow_html=True,
            )
    _sync_inpaint_selection_to_settings(source_path=source_path, mask_path=mask_path)
    with Image.open(source_path) as source_img:
        base_img = source_img.convert("RGBA")
    max_preview_w = 1024
    preview_img = base_img.copy()
    if preview_img.width > max_preview_w:
        ratio = max_preview_w / preview_img.width
        preview_img = preview_img.resize((max_preview_w, max(1, int(preview_img.height * ratio))))
    is_uploaded_preview = _is_uploaded_inpaint_preview_source(source_path=source_path, uploaded_source_path_value=uploaded_source_path_value)
    if is_uploaded_preview:
        badge_text = _inpaint_preview_source_badge_text(is_uploaded_preview=is_uploaded_preview)
        st.markdown(
            "<span style='display:inline-block;padding:0.18rem 0.55rem;border-radius:999px;"
            "background:#ede9fe;color:#5b21b6;font-size:0.78rem;font-weight:700;"
            f"line-height:1.1'>{badge_text}</span>",
            unsafe_allow_html=True,
        )
    overlay_opacity = st.slider(
        "Mask overlay opacity",
        min_value=0.05,
        max_value=1.0,
        value=float(st.session_state.get("image_inpaint_overlay_opacity") or 0.43),
        step=0.05,
        key="image_inpaint_overlay_opacity",
    )
    overlay_color = st.color_picker(
        "Mask overlay color",
        value=str(st.session_state.get("image_inpaint_overlay_color") or "#ff4040"),
        key="image_inpaint_overlay_color",
    )
    draw_mode = st.radio(
        "Canvas tool",
        options=["brush", "eraser"],
        index=0 if str(st.session_state.get(_canvas_mode_key(selected_rel_path)) or "brush") != "eraser" else 1,
        key=_canvas_mode_key(selected_rel_path),
        horizontal=True,
    )
    tool_col, brush_col, info_col = st.columns([1.1, 1.0, 1.3])
    with tool_col:
        st.caption("Canvas actions")
        undo_clicked = st.button("Undo", key=f"undo_mask::{selected_rel_path}", width="stretch")
        clear_clicked = st.button("Clear", key=f"clear_mask::{selected_rel_path}", width="stretch")
    with brush_col:
        brush_width = st.slider("Brush width", min_value=4, max_value=128, value=int(st.session_state.get("image_inpaint_brush_width") or 24), step=2, key="image_inpaint_brush_width")
    with info_col:
        st.caption(_inpaint_preview_source_caption(source_label=source_label, is_uploaded_preview=is_uploaded_preview))
        st.caption(f"Mask target: {mask_path}")
        st.caption(f"Preview size: {preview_img.width}x{preview_img.height}")
        st.caption(f"Tool active: {'Eraser' if draw_mode == 'eraser' else 'Brush'}")
    if undo_clicked:
        _undo_canvas(selected_rel_path)
        st.rerun()
    if clear_clicked:
        _clear_canvas(selected_rel_path)
        _ui_success("Cleared all strokes from the mask editor.")
        st.rerun()
    revision = int(st.session_state.get(_canvas_rev_key(selected_rel_path)) or 0)
    current_state = _canvas_seed_state(selected_rel_path)
    auto_loaded_path = str(st.session_state.get(_canvas_auto_load_key(selected_rel_path)) or "").strip()
    saved_mask_value = str(
        st.session_state.get(IMAGE_INPAINT_MASK_PATH_KEY)
        or st.session_state.get("image_local_inpaint_mask")
        or (mask_path if mask_path.is_file() else "")
    ).strip()
    if saved_mask_value and saved_mask_value != auto_loaded_path and not current_state.get("objects"):
        saved_path = Path(saved_mask_value)
        if saved_path.is_file():
            _load_saved_mask_into_editor(
                selected_rel_path=selected_rel_path,
                saved_path=saved_path,
                preview_size=preview_img.size,
            )
            _sync_inpaint_selection_to_settings(source_path=source_path, mask_path=saved_path)
            revision = int(st.session_state.get(_canvas_rev_key(selected_rel_path)) or 0)
            current_state = _canvas_seed_state(selected_rel_path)
            _ui_info("Loaded the saved mask into the editor automatically.")
    canvas_key = f"image_inpaint_canvas::{selected_rel_path}::rev{revision}"
    bg_rgb = ImageOps.autocontrast(preview_img.convert("RGB"))
    canvas_result = st_canvas(
        fill_color="rgba(255,255,255,1.0)",
        stroke_width=int(brush_width),
        stroke_color="#FFFFFF" if draw_mode != "eraser" else "rgba(0,0,0,1.0)",
        background_image=bg_rgb,
        update_streamlit=True,
        height=preview_img.height,
        width=preview_img.width,
        drawing_mode="freedraw",
        display_toolbar=False,
        initial_drawing=current_state,
        key=canvas_key,
    )
    json_data = canvas_result.json_data if isinstance(getattr(canvas_result, "json_data", None), dict) else None
    if isinstance(json_data, dict):
        prev_json = st.session_state.get(_canvas_json_key(selected_rel_path))
        if json_data != prev_json:
            _set_canvas_state(selected_rel_path, json_data)
            _push_canvas_history(selected_rel_path, json_data)
    preview_section = st.container()
    action_section = st.container()
    export_section = st.container()
    mask_path_value = mask_path
    mask = None
    overlay_image = None
    detector_preview_payload: dict[str, Any] = {"regions": [], "boxed": None, "crops": [], "preview": None}
    canvas_mask = _canvas_image_to_mask(canvas_result.image_data)
    if canvas_mask is not None:
        mask = canvas_mask
        if mask.getbbox() is not None:
            if preview_img.size != base_img.size:
                mask = mask.resize(base_img.size, resample=Image.Resampling.NEAREST)
            source_rgb = base_img.convert("RGB")
            overlay_tint = _hex_to_rgb(overlay_color)
            overlay_alpha = max(0, min(255, int(float(overlay_opacity) * 255)))
            overlay = overlay_mask_preview(image=source_rgb, mask=mask, tint=overlay_tint, alpha=overlay_alpha)
            overlay_image = overlay
            preview_overlay = overlay_mask_preview(
                image=preview_img.convert("RGB"),
                mask=mask.resize(preview_img.size, resample=Image.Resampling.NEAREST),
                tint=overlay_tint,
                alpha=overlay_alpha,
            )
            with preview_section:
                st.markdown("#### Inpaint mask preview")
                before_col, mask_col, after_col = st.columns([1.0, 1.0, 1.0])
                with before_col:
                    st.image(source_rgb, caption="Before overlay", width="stretch")
                with mask_col:
                    st.image(mask, caption="Mask", width="stretch")
                with after_col:
                    st.image(overlay, caption="After overlay", width="stretch")
                with st.expander("Canvas-sized overlay preview", expanded=False):
                    st.image(preview_overlay, caption="Overlay aligned to the current canvas size", width="stretch")
            with action_section:
                action_left, action_right = st.columns([1.0, 1.0])
                with action_left:
                    st.caption(f"Mask target: {mask_path_value}")
                with action_right:
                    if st.button("Save mask to bundle", key=f"save_mask::{selected_rel_path}", width="stretch"):
                        mask.save(mask_path_value)
                        st.session_state[_canvas_auto_load_key(selected_rel_path)] = str(mask_path_value)
                        _sync_inpaint_selection_to_settings(source_path=source_path, mask_path=mask_path_value)
                        st.session_state[IMAGE_INPAINT_SOURCE_PATH_KEY] = str(source_path)
                        st.session_state[IMAGE_INPAINT_MASK_PATH_KEY] = str(mask_path_value)
                        _ui_success(f"Saved mask into bundle: {mask_path_value}")
        else:
            with preview_section:
                _ui_info("Draw the inpaint region on top of the source image.")
    saved_mask = str(
        st.session_state.get(IMAGE_INPAINT_MASK_PATH_KEY)
        or st.session_state.get("image_local_inpaint_mask")
        or (mask_path_value if mask_path_value.is_file() else "")
    ).strip()
    if saved_mask:
        st.caption(f"Current mask: {saved_mask}")
        saved_path = Path(saved_mask)
        if saved_path.is_file():
            try:
                with Image.open(saved_path) as saved_img:
                    saved_mask_img = saved_img.convert("L")
                header_col, status_col = st.columns([1.8, 1.0])
                with header_col:
                    st.markdown("#### Saved mask overlay")
                with status_col:
                    saved_name = saved_path.name
                    auto_loaded_name = Path(auto_loaded_path).name if auto_loaded_path else ""
                    if auto_loaded_name and auto_loaded_name == saved_name:
                        st.markdown(
                            f"<span style='display:inline-block;padding:0.18rem 0.55rem;border-radius:999px;"
                            f"background:#dcfce7;color:#166534;font-size:0.78rem;font-weight:700;"
                            f"line-height:1.1'>Auto-loaded</span> "
                            f"<span style='font-size:0.78rem;color:#475569;font-weight:600'>{saved_name}</span>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"<span style='display:inline-block;padding:0.18rem 0.55rem;border-radius:999px;"
                            f"background:#ffedd5;color:#9a3412;font-size:0.78rem;font-weight:700;"
                            f"line-height:1.1'>Saved only</span> "
                            f"<span style='font-size:0.78rem;color:#475569;font-weight:600'>{saved_name}</span>",
                            unsafe_allow_html=True,
                        )
                saved_left, saved_mid, saved_right = st.columns([1.0, 1.0, 1.0])
                with saved_left:
                    st.image(saved_mask_img, caption="Saved mask", width="stretch")
                with saved_mid:
                    st.image(
                        overlay_mask_preview(
                            image=base_img.convert("RGB"),
                            mask=saved_mask_img,
                            tint=_hex_to_rgb(str(st.session_state.get("image_inpaint_overlay_color") or "#ff4040")),
                            alpha=max(0, min(255, int(float(st.session_state.get("image_inpaint_overlay_opacity") or 0.43) * 255))),
                        ),
                        caption="Saved mask overlay",
                        width="stretch",
                    )
                with saved_right:
                    st.caption("Saved mask is ready to push back into Settings.")
                    if st.button("Load saved mask into editor", key=f"load_saved_mask::{selected_rel_path}", width="stretch"):
                        _load_saved_mask_into_editor(
                            selected_rel_path=selected_rel_path,
                            saved_path=saved_path,
                            preview_size=preview_img.size,
                        )
                        st.session_state[_canvas_auto_load_key(selected_rel_path)] = str(saved_path)
                        _sync_inpaint_selection_to_settings(source_path=source_path, mask_path=saved_path)
                        _ui_success("Loaded saved mask into the editor.")
                        st.rerun()
            except Exception as exc:
                _ui_warning(f"Could not read the saved mask for preview: {_normalize_exc(exc)}")
    detector_preview_payload = _render_detector_preview(
        source_image=base_img.convert("RGB"),
        provider_payload=provider_payload,
        selected_rel_path=selected_rel_path,
    )
    with export_section:
        st.markdown("#### Debug preview sheet export")
        image_key = str((selected.get("prompt_data") or {}).get("image_key") or Path(selected_rel_path).stem).strip() or Path(selected_rel_path).stem
        export_path = _preview_sheet_export_path(prompt_dir, selected_rel_path, image_key)
        detector_regions = list(detector_preview_payload.get("regions") or [])
        detector_boxed = detector_preview_payload.get("boxed")
        detector_crops = list(detector_preview_payload.get("crops") or [])
        if overlay_image is None and saved_mask:
            saved_path = Path(saved_mask)
            if saved_path.is_file():
                try:
                    with Image.open(saved_path) as saved_img:
                        overlay_image = overlay_mask_preview(
                            image=base_img.convert("RGB"),
                            mask=saved_img.convert("L"),
                            tint=_hex_to_rgb(str(st.session_state.get("image_inpaint_overlay_color") or "#ff4040")),
                            alpha=max(0, min(255, int(float(st.session_state.get("image_inpaint_overlay_opacity") or 0.43) * 255))),
                        )
                except Exception:
                    overlay_image = None
        export_lines = [
            f"Prompt: {selected_rel_path}",
            f"Source: {source_path}",
            f"Overlay color: {str(st.session_state.get('image_inpaint_overlay_color') or '#ff4040')} | opacity={float(st.session_state.get('image_inpaint_overlay_opacity') or 0.43):.2f}",
            f"Detector: {provider_payload.get('local_adetailer_detector') or '-'} | Regions: {len(detector_regions)}",
        ]
        if st.button("Export preview sheet to bundle", key=f"export_preview_sheet::{selected_rel_path}", width="stretch"):
            try:
                mask_for_sheet = mask.convert("L") if isinstance(mask, Image.Image) else None
                if mask_for_sheet is None and saved_mask and Path(saved_mask).is_file():
                    with Image.open(saved_mask) as saved_img:
                        mask_for_sheet = saved_img.convert("L")
                sheet = build_debug_preview_sheet(
                    source_image=base_img.convert("RGB"),
                    overlay_image=overlay_image if isinstance(overlay_image, Image.Image) else None,
                    boxed_image=detector_boxed if isinstance(detector_boxed, Image.Image) else None,
                    mask_image=mask_for_sheet,
                    crops=detector_crops,
                    header_lines=export_lines,
                )
                sheet.save(export_path)
                st.session_state["image_last_preview_sheet"] = str(export_path)
                _ui_success(f"Exported preview sheet: {export_path}")
                st.image(sheet, caption="Exported preview sheet", width="stretch")
            except Exception as exc:
                _ui_warning(f"Could not export preview sheet: {_normalize_exc(exc)}")
        else:
            st.caption(f"Export target: {export_path}")
def render_doctor_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    st.subheader("Image doctor")
    prompt_dir, entries, issues = _resolve_test_prompt_bundle(settings)
    provider_status = local_provider_status(settings)
    c1, c2, c3 = st.columns(3)
    c1.metric("Provider", str(settings.get("provider") or "-"))
    c2.metric("Prompt files", len(entries))
    c3.metric("Issues", len(issues))
    rows = [
        {"check": "Prompt directory", "status": "OK" if prompt_dir and prompt_dir.exists() else "missing", "detail": str(prompt_dir or "-")},
        {"check": "Output directory", "status": "OK" if str(st.session_state.get("image_output_dir") or "").strip() else "missing", "detail": str(st.session_state.get("image_output_dir") or "Output directory not configured")},
        {"check": "Story handoff dir", "status": "OK" if str(workspace_handoff_state(st.session_state).story_image_handoff_dir or "").strip() else "missing", "detail": str(workspace_handoff_state(st.session_state).story_image_handoff_dir or "Story handoff directory not available")},
        {"check": "Local model", "status": "OK" if str(provider_status.get("requested_model") or provider_status.get("resolved_model") or "").strip() else "missing", "detail": str(provider_status.get("resolved_model") or provider_status.get("requested_model") or "Local model not configured")},
    ]
    st.dataframe(rows, width="stretch", height=210)
    for issue in issues:
        st.warning(issue)
    if not issues:
        st.success("Prompt bundle is valid for test/generate.")
    render_runtime_diagnostics_block({
        "provider_status": provider_status,
        "settings": {
            "provider": settings.get("provider"),
            "base_url": settings.get("base_url"),
            "output_dir": settings.get("output_dir"),
            "input_dir": settings.get("input_dir"),
            "handoff_dir": settings.get("handoff_dir"),
            "source_kind": st.session_state.get("image_source_kind"),
        },
        "prompt_bundle": {
            "prompt_dir": str(prompt_dir or ""),
            "entry_count": len(entries),
            "issues": issues,
        },
    }, label="Image diagnostics summary", expanded=False)
def render_inputs_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    _prefill_from_story_handoff()
    st.subheader("Inputs")
    _render_image_focus_hint("Inputs")
    st.checkbox(
        "Lock input to Story handoff",
        key="image_lock_to_story_handoff",
        help="When enabled, Image keeps following the newest handoff bundle sent from Story.",
    )
    st.radio(
        "Load JSON prompts from",
        options=["handoff", "input"],
        key="image_source_kind",
        horizontal=True,
        format_func=lambda value: "handoff" if value == "handoff" else "input",
    )
    prompt_dir = _resolve_prompt_dir(settings)
    source_label = "handoff" if str(st.session_state.get("image_source_kind") or "handoff") == "handoff" else "input"
    if prompt_dir and prompt_dir.is_dir():
        st.success(f"Using {source_label} folder: {prompt_dir}")
        manifest_path = prompt_dir / "manifest.json"
        if manifest_path.is_file():
            with st.expander("Manifest", expanded=False):
                st.json(json.loads(manifest_path.read_text(encoding="utf-8")))
    else:
        show_path_warning(
            f"{source_label} prompt directory",
            path_value=str(prompt_dir or ""),
            actions=[
                "Check the source folder again in the sidebar or enable Story handoff.",
                "Make sure the folder exists before opening Prompt/Test/Run.",
            ],
        )
    entries = _load_prompt_entries(prompt_dir)
    if not entries:
        show_empty_result("prompt bundle", actions=["Check the source folder or Story handoff again.", "Make sure cover_prompt.json, *_prompt.json, or scene_prompts/*.json already exists."])
        return
    _ensure_prompt_edit_state(entries, prompt_dir)
    st.caption(f"The current bundle contains {len(entries)} prompt(s). Use the Prompt tab to inspect or edit before rendering.")
def render_prompt_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    _prefill_from_story_handoff()
    st.subheader("Prompt editor")
    prompt_dir, entries, issues = _resolve_test_prompt_bundle(settings)
    for issue in issues:
        show_path_warning(
            "prompt bundle",
            path_value=str(prompt_dir or ""),
            actions=[issue, "Check the prompt source and prompt directory in the sidebar again."],
        )
    if not entries:
        show_empty_result(
            "prompt bundle",
            actions=[
                "Check the prompt source and prompt directory in the sidebar again.",
                "Create cover_prompt.json, *_prompt.json, or scene_prompts/*.json before editing.",
            ],
        )
        return
    _ensure_prompt_edit_state(entries, prompt_dir)
    selected_rel_path = st.selectbox(
        "Choose prompt",
        options=[entry["rel_path"] for entry in entries],
        format_func=lambda value: next((f"{entry['slot']} ({entry['rel_path']})" for entry in entries if entry['rel_path'] == value), value),
        key="image_prompt_selected_entry",
    )
    selected = next(entry for entry in entries if entry["rel_path"] == selected_rel_path)
    prompt_data = dict(selected.get("prompt_data") or {})
    effective = _get_effective_prompt_edit(selected_rel_path, prompt_data)
    meta_col, action_col = st.columns([1.5, 1.0])
    with meta_col:
        st.caption(f"Prompt source: {prompt_dir or '-'}")
        st.write({
            "slot": selected.get("slot"),
            "kind": selected.get("kind"),
            "file": selected_rel_path,
            "image_key": prompt_data.get("image_key"),
        })
    with action_col:
        st.button(
            "Reset this prompt",
            key=f"reset_prompt::{selected_rel_path}",
            on_click=_reset_prompt_edit_state,
            args=(
                selected_rel_path,
            ),
            kwargs={
                "prompt": str(prompt_data.get("prompt") or ""),
                "negative_prompt": str(prompt_data.get("negative_prompt") or ""),
                "provider_payload_json": _format_provider_payload_json(prompt_data.get("provider_payload")),
            },
        )
        st.button(
            "Reset all prompts",
            key="reset_all_prompts",
            on_click=lambda: [
                _reset_prompt_edit_state(
                    entry["rel_path"],
                    prompt=str((entry.get("prompt_data") or {}).get("prompt") or ""),
                    negative_prompt=str((entry.get("prompt_data") or {}).get("negative_prompt") or ""),
                    provider_payload_json=_format_provider_payload_json((entry.get("prompt_data") or {}).get("provider_payload")),
                )
                for entry in entries
            ],
        )
    prompt_value = st.text_area(
        "Prompt",
        value=str(effective.get("prompt") or ""),
        height=220,
        key=f"image_prompt_text::{selected_rel_path}",
    )
    prompt_auto_shorten_enabled = _render_prompt_autoshorten_toggle(
        label="Prompt auto-shortened",
        state_key="image_local_auto_shorten_prompt",
        widget_key="image_prompt_auto_shorten_toggle",
        help_text="If enabled, the Prompt field will be trimmed before generation when it exceeds the CLIP limit.",
    )
    _render_prompt_autoshorten_status("Prompt", enabled=prompt_auto_shorten_enabled)
    _render_clip_token_estimate("Prompt estimate", prompt_value, key_suffix=f"editor_prompt::{selected_rel_path}")
    negative_value = st.text_area(
        "Negative prompt",
        value=str(effective.get("negative_prompt") or ""),
        height=140,
        key=f"image_negative_text::{selected_rel_path}",
    )
    negative_auto_shorten_enabled = _render_prompt_autoshorten_toggle(
        label="Negative prompt auto-shortened",
        state_key="image_local_auto_shorten_negative_prompt",
        widget_key="image_negative_auto_shorten_toggle",
        help_text="If enabled, the Negative prompt field will be trimmed before generation when it exceeds the CLIP limit.",
    )
    _render_prompt_autoshorten_status("Negative prompt", enabled=negative_auto_shorten_enabled)
    _render_clip_token_estimate("Negative estimate", negative_value, key_suffix=f"editor_negative::{selected_rel_path}")
    _render_prompt_trim_preview_block(
        prompt_value,
        negative_value,
        selected_rel_path=selected_rel_path,
        prompt_enabled=prompt_auto_shorten_enabled,
        negative_enabled=negative_auto_shorten_enabled,
    )
    provider_payload_json_value = str(effective.get("provider_payload_json") or "")
    with st.expander("Advanced provider payload override", expanded=bool(provider_payload_json_value)):
        provider_payload_json_value = st.text_area(
            "Provider payload JSON",
            value=provider_payload_json_value,
            height=150,
            key=f"image_provider_payload_text::{selected_rel_path}",
            help="Optional JSON object merged into this prompt's provider_payload during generation.",
        )
        provider_payload_preview, provider_payload_error = _parse_provider_payload_json(provider_payload_json_value)
        if provider_payload_error:
            _ui_error(provider_payload_error)
        elif provider_payload_preview:
            st.caption(f"Provider payload override keys: {', '.join(sorted(provider_payload_preview.keys()))}")
        else:
            st.caption("No provider payload override for this prompt.")
    _store_prompt_edit_state(
        selected_rel_path,
        prompt=prompt_value,
        negative_prompt=negative_value,
        provider_payload_json=provider_payload_json_value,
    )
    with st.expander("Original prompt JSON", expanded=False):
        st.json(prompt_data)
def render_run_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    _prefill_from_story_handoff()
    prompt_dir, entries, issues = _resolve_test_prompt_bundle(settings)
    output_dir_raw = str(settings.get("output_dir") or st.session_state.get("image_output_dir") or "").strip()
    result = st.session_state.get("image_last_result")
    errors: list[str] = list(issues)
    if prompt_dir is None:
        if not errors:
            errors.append("Choose a source directory for JSON prompts.")
    elif not prompt_dir.is_dir():
        errors.append(f"Prompt directory not found: {prompt_dir}")
    elif not entries:
        errors.append("Prompt directory is valid but contains no prompt file to generate.")
    if not output_dir_raw:
        errors.append("Enter an Image output directory.")
    for err in errors:
        _ui_error(err)
    st.caption(f"Current prompt source: {prompt_dir or '-'}")
    if entries:
        st.caption(f"Prompt(s) available for generate: {len(entries)}")
        edited_count = 0
        for entry in entries:
            prompt_data = dict(entry.get("prompt_data") or {})
            effective = _get_effective_prompt_edit(entry["rel_path"], prompt_data)
            if str(effective.get("prompt") or "") != str(prompt_data.get("prompt") or "") or str(effective.get("negative_prompt") or "") != str(prompt_data.get("negative_prompt") or ""):
                edited_count += 1
        st.caption(f"Prompt(s) currently ready to render: {edited_count}")
    prompt_total = len(entries)
    progress = st.progress(0.0, text=format_progress_text(0, "Ready", [f"prompts={prompt_total}"]))
    status = st.empty()
    if st.button("Generate images", type="primary", width="stretch", disabled=bool(errors)):
        if prompt_dir is None:
            _ui_error("Prompt directory could not be resolved for generate.")
            return
        prompt_overrides = _collect_prompt_override_payload(entries)
        request = RenderImageRequest(
            provider=str(settings.get("provider") or ""),
            handoff_dir=prompt_dir,
            output_dir=_resolve_workspace_path(output_dir_raw),
            base_url=str(settings.get("base_url") or ""),
            api_key=str(settings.get("api_key") or ""),
            workflow_json_file=str(settings.get("workflow_json_file") or ""),
            cover_workflow_json_file=str(settings.get("cover_workflow_json_file") or ""),
            scene_workflow_json_file=str(settings.get("scene_workflow_json_file") or ""),
            fallback_workflow_json_file=str(settings.get("fallback_workflow_json_file") or ""),
            auto_select_workflow_by_kind=bool(settings.get("auto_select_workflow_by_kind", True)),
            positive_prompt_node_id=str(settings.get("positive_prompt_node_id") or "2"),
            negative_prompt_node_id=str(settings.get("negative_prompt_node_id") or "3"),
            sampler_node_id=str(settings.get("sampler_node_id") or "5"),
            latent_size_node_id=str(settings.get("latent_size_node_id") or "4"),
            output_node_ids=str(settings.get("output_node_ids") or "7"),
            poll_interval=float(settings.get("poll_interval") or 1.5),
            max_wait_s=int(settings.get("max_wait_s") or 180),
            width=int(settings.get("width") or 512),
            height=int(settings.get("height") or 512),
            steps=int(settings.get("steps") or 30),
            cfg=float(settings.get("cfg") or 6.5),
            sampler_name=str(settings.get("sampler_name") or "dpmpp_2m"),
            scheduler=str(settings.get("scheduler") or "karras"),
            seed=int(settings.get("seed") or -1),
            negative_prompt=str(settings.get("negative_prompt") or ""),
            local_model_id_or_path=str(settings.get("local_model_id_or_path") or ""),
            local_device=str(settings.get("local_device") or "cuda"),
            local_dtype=str(settings.get("local_dtype") or "auto"),
            local_variant=str(settings.get("local_variant") or ""),
            local_use_safetensors=bool(settings.get("local_use_safetensors", True)),
            local_enable_attention_slicing=bool(settings.get("local_enable_attention_slicing", True)),
            local_enable_model_cpu_offload=bool(settings.get("local_enable_model_cpu_offload", False)),
            provider_payload=dict(settings.get("provider_payload") or {}),
            prompt_overrides=prompt_overrides,
        )
        try:
            update_global_run_monitor(app="Image", stage="Generate", status="running", progress=10, summary={"provider": request.provider, "prompt_count": prompt_total, "generated": 0})
            append_global_run_event(app="Image", stage="Generate", status="running", message=f"provider={request.provider}")
            progress.progress(0.05, text=format_progress_text(5, "Starting image generation", [f"provider={request.provider}", f"prompts={prompt_total}"]))
            generated_count = 0

            def callback(done: float, message: str = "") -> None:
                nonlocal generated_count
                frac = max(0.0, min(1.0, float(done) / 100.0))
                if str(message or "").startswith("Finished "):
                    generated_count = min(prompt_total, generated_count + 1)
                percent = int(round(frac * 100))
                detail_text = format_progress_text(
                    percent,
                    message or "Processing",
                    [f"provider={request.provider}", f"prompts={prompt_total}", f"generated={generated_count}"],
                )
                progress.progress(frac, text=detail_text)
                status.info(detail_text)
                render_runtime_usage_compact()
                update_global_run_monitor(
                    app="Image",
                    stage="Generate",
                    status="running",
                    progress=percent,
                    summary={"provider": request.provider, "prompt_count": prompt_total, "generated": generated_count},
                )

            result = run_image_job(request, progress_callback=callback)
            st.session_state["image_last_result"] = result
            st.session_state["image_last_error"] = ""
            st.session_state["image_last_logs"] = result.logs
            workspace_source_outputs(st.session_state).image_cover_output = str(result.cover_image or "")
            images_dir = str(getattr(result, "images_dir", None) or result.scene_images_dir)
            workspace_source_outputs(st.session_state).image_scenes_dir = images_dir
            set_image_handoff(cover_image_path=str(result.cover_image or ""), scene_images_dir=images_dir, manifest_path=str(result.manifest_path or ""))
            update_global_run_monitor(app="Image", stage="Generate", status="completed", progress=100, output_path=str(result.output_dir), summary={"generated": len(result.generated_files)})
            append_global_run_event(app="Image", stage="Generate", status="completed", message=f"generated={len(result.generated_files)}", output_path=str(result.output_dir))
            progress.progress(1.0, text=format_progress_text(100, "Complete", [f"provider={result.provider}", f"generated={len(result.generated_files)}"]))
            status.success(format_progress_text(100, f"Generated {len(result.generated_files)} image(s)", [f"provider={result.provider}"]))
            append_deduped_tail_history_entry(
                IMAGE_RUN_HISTORY_KEY,
                {
                    "provider": result.provider,
                    "output_dir": str(result.output_dir),
                    "cover_image": str(result.cover_image or ""),
                    "scene_images_dir": str(result.scene_images_dir),
                    "generated_count": len(result.generated_files),
                    "manifest_path": str(result.manifest_path or ""),
                },
                limit=20,
            )
            _ui_success(f"Generated {len(result.generated_files)} image(s).")
        except Exception as exc:
            st.session_state["image_last_error"] = str(exc)
            update_global_run_monitor(app="Image", stage="Generate", status="failed", progress=100, error_text=str(exc))
            append_global_run_event(app="Image", stage="Generate", status="failed", message="Image generation failed", error_text=str(exc))
            progress.progress(1.0, text=format_progress_text(100, "Failed", [f"provider={request.provider}", f"prompts={prompt_total}"]))
            status.error(f"Failed: {_normalize_exc(exc)}")
            _ui_error(_normalize_exc(exc))
            result = st.session_state.get("image_last_result")
    preview_output_dir = output_dir_raw or str(getattr(st.session_state.get("image_last_result"), "output_dir", "") or "")
    _render_prompt_cards_in_run(settings, prompt_dir, entries, result)
    preview_result = _build_existing_run_preview_result(preview_output_dir)
    if preview_result is not None:
        st.markdown("### Versioned preview")
        _render_result_preview_panel(preview_result, settings=settings, prompt_dir=prompt_dir, entries=entries, key_prefix="run_latest")


def render_test_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    st.subheader("Test")
    prompt_dir, entries, issues = _resolve_test_prompt_bundle(settings)
    st.caption(f"Current prompt source: {prompt_dir or '-'}")
    for issue in issues:
        show_path_warning(
            "prompt bundle",
            path_value=str(prompt_dir or ""),
            actions=[issue, "Check the prompt source and prompt directory again in Inputs/Sidebar."],
        )
    if not entries:
        show_empty_result(
            "testable prompt bundle",
            actions=[
                "Check the prompt source and prompt directory again in Inputs/Sidebar.",
                "Make sure the bundle was created from Story or a valid input directory.",
            ],
        )
        return
    st.metric("Available prompts", len(entries))
    selected_rel_path = st.selectbox(
        "Choose a prompt to inspect",
        options=[entry["rel_path"] for entry in entries],
        format_func=lambda value: next((f"{entry['slot']} ({entry['rel_path']})" for entry in entries if entry['rel_path'] == value), value),
        key="image_test_selected_prompt",
    )
    selected = next(entry for entry in entries if entry["rel_path"] == selected_rel_path)
    prompt_data = dict(selected["prompt_data"] or {})
    effective = _get_effective_prompt_edit(selected_rel_path, prompt_data)
    left, right = st.columns([1.3, 1.0])
    with left:
        st.text_area("Effective prompt", value=str(effective.get("prompt") or ""), height=220, disabled=True, key=f"image_test_effective::{selected_rel_path}")
        st.text_area("Effective negative prompt", value=str(effective.get("negative_prompt") or ""), height=120, disabled=True, key=f"image_test_negative::{selected_rel_path}")
    with right:
        st.write({
            "slot": selected.get("slot"),
            "kind": prompt_data.get("kind") or selected.get("kind"),
            "source_file": selected_rel_path,
            "width": int(settings.get("width") or 512),
            "height": int(settings.get("height") or 512),
            "steps": int(settings.get("steps") or 30),
            "cfg": float(settings.get("cfg") or 6.5),
        })
    if st.button("Validate prompt bundle", key="image_test_validate_bundle", width="stretch"):
        missing = [
            entry["rel_path"]
            for entry in entries
            if not str(_get_effective_prompt_edit(entry["rel_path"], entry["prompt_data"]).get("prompt") or "").strip()
        ]
        if missing:
            _ui_error("Some prompts are empty: " + ", ".join(missing))
        else:
            _ui_success(f"Bundle is valid: {len(entries)} prompt(s) are ready to generate.")
    if str(settings.get("provider") or "") == "stable_diffusion_local":
        with st.expander("ADetailer detector preview", expanded=False):
            _render_adetailer_preview_for_entry(settings, prompt_dir, selected, section_key="test_preview")
def render_preview_logs_tab(settings: dict[str, Any]) -> None:
    st.subheader("Latest result")
    result = st.session_state.get("image_last_result")
    _render_result_preview_panel(result, settings=settings, prompt_dir=_resolve_prompt_dir(settings), entries=_load_prompt_entries(_resolve_prompt_dir(settings)), key_prefix="preview_logs")
def render_history_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    st.subheader("Image run history")
    rows = list(st.session_state.get(IMAGE_RUN_HISTORY_KEY) or [])
    if not rows:
        show_empty_result(
            "image run history",
            actions=["Run a job in the Run tab to create render history.", "Return to this tab after cover/scenes have been generated."],
        )
        return
    display_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(reversed(rows), start=1):
        output_dir = str(row.get("output_dir") or "")
        display_rows.append({
            "#": idx,
            "provider": row.get("provider", ""),
            "generated": row.get("generated_count", 0),
            "output_dir": output_dir,
            "cover_image": row.get("cover_image", ""),
            "scene_images_dir": row.get("scene_images_dir", ""),
            "manifest_path": row.get("manifest_path", ""),
        })
    st.dataframe(display_rows, width="stretch", height=320)
    option_labels = [f"#{len(rows) - idx} | {str(row.get('provider') or '-')} | {str(row.get('output_dir') or '-')}" for idx, row in enumerate(rows)]
    selected_label = st.selectbox("Choose history entry", options=option_labels, index=len(option_labels) - 1, key="image_history_selected")
    selected_index = option_labels.index(selected_label)
    selected = rows[selected_index]
    class _HistoryResult:
        def __init__(self, row: dict[str, Any]):
            self.provider = row.get("provider", "")
            self.output_dir = Path(str(row.get("output_dir") or ""))
            self.cover_image = Path(str(row.get("cover_image") or "")) if str(row.get("cover_image") or "").strip() else None
            self.scene_images_dir = Path(str(row.get("scene_images_dir") or ""))
            self.generated_files = _list_image_files(self.scene_images_dir)
            self.manifest_path = Path(str(row.get("manifest_path") or "")) if str(row.get("manifest_path") or "").strip() else None
            self.logs = []
    history_result = _HistoryResult(selected)
    _render_result_preview_panel(history_result, settings=settings, prompt_dir=None, entries=None, key_prefix="history_preview")
    with st.expander("Selected history entry", expanded=False):
        st.json(selected)

