from __future__ import annotations

from typing import Any

import streamlit as st


def _prompt_bundle_key(prompt_dir: Any) -> str:
    return str(prompt_dir or "").strip()


def _ensure_prompt_edit_state(entries: list[dict[str, Any]], prompt_dir: Any = None) -> dict[str, dict[str, Any]]:
    bundle_key = _prompt_bundle_key(prompt_dir)
    if bundle_key:
        previous_bundle_key = str(st.session_state.get("image_prompt_edit_bundle_key") or "")
        if previous_bundle_key and previous_bundle_key != bundle_key:
            st.session_state["image_prompt_edit_map"] = {}
            st.session_state["image_prompt_overrides"] = {}
        st.session_state["image_prompt_edit_bundle_key"] = bundle_key

    current = dict(st.session_state.get("image_prompt_edit_map") or {})
    changed = False
    for entry in entries:
        rel_path = entry["rel_path"]
        if rel_path in current and isinstance(current[rel_path], dict):
            continue
        prompt_data = dict(entry.get("prompt_data") or {})
        current[rel_path] = {
            "prompt": str(prompt_data.get("prompt") or ""),
            "negative_prompt": str(prompt_data.get("negative_prompt") or ""),
        }
        changed = True
    if changed:
        st.session_state["image_prompt_edit_map"] = current
    return current


def _store_prompt_edit_state(
    rel_path: str,
    *,
    prompt: str,
    negative_prompt: str,
) -> None:
    prompt_value = str(prompt)
    negative_value = str(negative_prompt)

    edit_map = dict(st.session_state.get("image_prompt_edit_map") or {})
    edit_map[rel_path] = {
        "prompt": prompt_value,
        "negative_prompt": negative_value,
    }
    st.session_state["image_prompt_edit_map"] = edit_map

    legacy_overrides = dict(st.session_state.get("image_prompt_overrides") or {})
    legacy_overrides[rel_path] = prompt_value
    st.session_state["image_prompt_overrides"] = legacy_overrides

def _sync_prompt_widget_state(
    rel_path: str,
    *,
    prompt: str,
    negative_prompt: str,
) -> None:
    st.session_state[f"image_prompt_text::{rel_path}"] = str(prompt)
    st.session_state[f"image_negative_text::{rel_path}"] = str(negative_prompt)


def _reset_prompt_edit_state(
    rel_path: str,
    *,
    prompt: str,
    negative_prompt: str,
) -> None:
    _store_prompt_edit_state(rel_path, prompt=prompt, negative_prompt=negative_prompt)
    _sync_prompt_widget_state(rel_path, prompt=prompt, negative_prompt=negative_prompt)


def _get_effective_prompt_edit(rel_path: str, prompt_data: dict[str, Any]) -> dict[str, Any]:
    edit_map = dict(st.session_state.get("image_prompt_edit_map") or {})
    edit = edit_map.get(rel_path)
    if isinstance(edit, dict):
        prompt_fallback = str(prompt_data.get("prompt") or "")
        negative_fallback = str(prompt_data.get("negative_prompt") or "")
        return {
            "prompt": str(edit["prompt"]) if "prompt" in edit else prompt_fallback,
            "negative_prompt": str(edit["negative_prompt"]) if "negative_prompt" in edit else negative_fallback,
        }
    legacy_overrides = dict(st.session_state.get("image_prompt_overrides") or {})
    if rel_path in legacy_overrides:
        legacy = legacy_overrides.get(rel_path)
        return {
            "prompt": str(legacy) if legacy is not None else "",
            "negative_prompt": str(prompt_data.get("negative_prompt") or ""),
        }
    return {
        "prompt": str(prompt_data.get("prompt") or ""),
        "negative_prompt": str(prompt_data.get("negative_prompt") or ""),
    }


def _collect_prompt_override_payload(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for entry in entries:
        rel_path = entry["rel_path"]
        prompt_data = dict(entry.get("prompt_data") or {})
        effective = _get_effective_prompt_edit(rel_path, prompt_data)
        payload[rel_path] = {
            "prompt": str(effective.get("prompt") or ""),
            "negative_prompt": str(effective.get("negative_prompt") or ""),
        }
    return payload

