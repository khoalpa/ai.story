from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from image.gui.shared_state import get_workspace_target_field
from image.gui.prompt_state import _get_effective_prompt_edit
from image.provider_runtime import (
    _resolve_bundle_asset_path,
    preview_prompt_shortening,
)
from image.workflow_routing import infer_prompt_kind


def _estimate_clip_tokens(text: str) -> int:
    import re

    raw = str(text or "").strip()
    if not raw:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", raw, flags=re.UNICODE))


def _clip_estimate_level(token_estimate: int, *, limit: int = 77) -> str:
    if token_estimate > limit:
        return "danger"
    if token_estimate >= max(64, limit - 13):
        return "warning"
    return "ok"


def _render_clip_token_estimate(label: str, text: str, *, limit: int = 77, key_suffix: str = "") -> None:
    estimate = _estimate_clip_tokens(text)
    level = _clip_estimate_level(estimate, limit=limit)
    color = {"ok": "#15803d", "warning": "#b45309", "danger": "#b91c1c"}[level]
    status = {"ok": "OK", "warning": "Near CLIP limit", "danger": "Over CLIP limit"}[level]
    detail = f"{label}: ~{estimate}/{limit} tokens | {status}"
    st.markdown(
        f"<div style='font-size:0.9rem;color:{color};font-weight:600;margin:0.2rem 0 0.45rem 0'>{detail}</div>",
        unsafe_allow_html=True,
    )


def _render_prompt_trim_status(label: str, text: str, *, enabled: bool, limit: int = 77, key_suffix: str = "") -> dict[str, Any]:
    preview = preview_prompt_shortening(text, limit=limit)
    shortened = bool(preview.get("was_shortened"))
    before = int(preview.get("before_tokens") or 0)
    after = int(preview.get("after_tokens") or 0)
    level = "danger" if before > limit else ("warning" if before >= max(64, limit - 13) else "ok")
    color = {"ok": "#15803d", "warning": "#b45309", "danger": "#b91c1c"}[level if shortened or before else "ok"]
    if not enabled:
        status = "disabled"
        color = "#b45309" if before else "#6b7280"
    else:
        status = "auto-shortened" if shortened else "unchanged"
    st.markdown(
        f"<div style='font-size:0.9rem;color:{color};font-weight:600;margin:0.15rem 0 0.45rem 0'>{label}: {status} | {before} -> {after} tokens</div>",
        unsafe_allow_html=True,
    )
    return preview


def _render_prompt_trim_preview_block(
    prompt_text: str,
    negative_text: str,
    *,
    selected_rel_path: str,
    prompt_enabled: bool,
    negative_enabled: bool,
    limit: int = 77,
) -> None:
    prompt_preview = _render_prompt_trim_status("Prompt", prompt_text, enabled=prompt_enabled, limit=limit, key_suffix=f"prompt::{selected_rel_path}")
    negative_preview = _render_prompt_trim_status("Negative prompt", negative_text, enabled=negative_enabled, limit=limit, key_suffix=f"negative::{selected_rel_path}")
    preview_key = f"image_prompt_trim_preview_open::{selected_rel_path}"
    auto_shorten_enabled = bool(prompt_enabled or negative_enabled)
    if st.button(
        "Preview trimmed prompt",
        key=f"preview_trimmed::{selected_rel_path}",
        width="stretch",
        disabled=not auto_shorten_enabled,
    ):
        st.session_state[preview_key] = not bool(st.session_state.get(preview_key))
    if not auto_shorten_enabled:
        st.caption("Auto-shortened is disabled for both fields, so runtime will keep the full prompt unchanged.")
    if st.session_state.get(preview_key):
        with st.container(border=True):
            st.caption("Trim preview uses the same clause-priority strategy as runtime: subject -> style -> camera -> lighting.")
            st.text_area("Trimmed prompt", value=str(prompt_preview.get("trimmed") or ""), height=180, disabled=True, key=f"trimmed_prompt::{selected_rel_path}")
            st.text_area("Trimmed negative prompt", value=str(negative_preview.get("trimmed") or ""), height=120, disabled=True, key=f"trimmed_negative::{selected_rel_path}")


def _render_prompt_autoshorten_status(field_label: str, *, enabled: bool) -> None:
    status = "Enabled" if enabled else "Disabled"
    color = "#15803d" if enabled else "#b45309"
    st.markdown(
        f"<div style='font-size:0.9rem;color:{color};font-weight:600;margin:0.15rem 0 0.45rem 0'>{field_label}: {status}</div>",
        unsafe_allow_html=True,
    )


def _render_prompt_autoshorten_toggle(*, label: str, state_key: str, widget_key: str, help_text: str) -> bool:
    current = bool(st.session_state.get(state_key, True))
    enabled = st.checkbox(
        label,
        value=current,
        key=widget_key,
        help=help_text,
    )
    st.session_state[state_key] = bool(enabled)
    return bool(enabled)


def _render_quick_input_previews(settings: dict[str, Any], prompt_dir: Path | None, entry: dict[str, Any], *, section_key: str, result: Any = None) -> None:
    provider_payload = dict(settings.get("provider_payload") or {})
    prompt_path = entry.get("path")
    prompt_data = dict(entry.get("prompt_data") or {})
    kind = str(entry.get("kind") or infer_prompt_kind(prompt_data, prompt_path) or "").strip().lower()
    suggested_output = Path(str(entry.get("suggested_output") or ""))

    primary_label = "Expected output"
    primary_path: Path | None = None
    if result is not None:
        try:
            from image.gui.result_ui import _resolve_result_output_for_entry

            primary_path = _resolve_result_output_for_entry(result, entry)
        except Exception:
            primary_path = None
    if primary_path is None or not primary_path.is_file():
        primary_path = suggested_output if suggested_output.is_file() else None
    if kind == "cover":
        primary_label = "Cover preview"
    elif kind == "scene":
        primary_label = "Scene preview"

    if primary_path is not None and primary_path.is_file():
        st.image(str(primary_path), caption=primary_label, width="stretch")
        st.caption(str(primary_path))
    else:
        st.caption(f"{primary_label}: no source image could be resolved for this prompt yet.")

    extra_candidates = [
        ("Init image", _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind="init_image")),
        ("Control image", _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind="control_image")),
        ("Inpaint source", _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind="inpaint_image")),
        ("Mask", _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind="mask_image")),
    ]
    available = [(label, path) for label, path in extra_candidates if path is not None and Path(path).is_file() and Path(path) != primary_path]
    if available:
        with st.expander("Extra resolved inputs", expanded=False):
            cols = st.columns(min(4, len(available)))
            for idx, (label, path_value) in enumerate(available):
                with cols[idx % len(cols)]:
                    st.image(str(path_value), caption=label, width="stretch")
                    st.caption(str(path_value))


def _render_image_focus_hint(view_name: str) -> None:
    if st.session_state.get("workspace_active_app") != "Image":
        return
    if st.session_state.get("image_embedded_view_selector") != view_name:
        return
    target_field = str(get_workspace_target_field("Image", "") or "").strip()
    if not target_field:
        return
    mapping = {"prompt_bundle": "Story handoff prompt bundle", "doctor": "Image Doctor"}
    st.info(f"Deep-link target: {mapping.get(target_field, target_field)}")

