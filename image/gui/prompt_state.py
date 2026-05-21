from __future__ import annotations

import json
from typing import Any

import streamlit as st


def _prompt_bundle_key(prompt_dir: Any) -> str:
    return str(prompt_dir or "").strip()


def _format_provider_payload_json(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _parse_provider_payload_json(raw_value: str) -> tuple[dict[str, Any], str]:
    text = str(raw_value or "").strip()
    if not text:
        return {}, ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"Provider payload JSON is invalid: {exc.msg} at line {exc.lineno}, column {exc.colno}."
    if not isinstance(parsed, dict):
        return {}, "Provider payload JSON must be a JSON object."
    return parsed, ""


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
            "provider_payload_json": _format_provider_payload_json(prompt_data.get("provider_payload")),
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
    provider_payload_json: str = "",
) -> None:
    prompt_value = str(prompt)
    negative_value = str(negative_prompt)
    provider_payload_json_value = str(provider_payload_json)

    edit_map = dict(st.session_state.get("image_prompt_edit_map") or {})
    edit_map[rel_path] = {
        "prompt": prompt_value,
        "negative_prompt": negative_value,
        "provider_payload_json": provider_payload_json_value,
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
    provider_payload_json: str = "",
) -> None:
    st.session_state[f"image_prompt_text::{rel_path}"] = str(prompt)
    st.session_state[f"image_negative_text::{rel_path}"] = str(negative_prompt)
    st.session_state[f"image_provider_payload_text::{rel_path}"] = str(provider_payload_json)


def _reset_prompt_edit_state(
    rel_path: str,
    *,
    prompt: str,
    negative_prompt: str,
    provider_payload_json: str = "",
) -> None:
    _store_prompt_edit_state(
        rel_path,
        prompt=prompt,
        negative_prompt=negative_prompt,
        provider_payload_json=provider_payload_json,
    )
    _sync_prompt_widget_state(
        rel_path,
        prompt=prompt,
        negative_prompt=negative_prompt,
        provider_payload_json=provider_payload_json,
    )


def _get_effective_prompt_edit(rel_path: str, prompt_data: dict[str, Any]) -> dict[str, Any]:
    edit_map = dict(st.session_state.get("image_prompt_edit_map") or {})
    edit = edit_map.get(rel_path)
    if isinstance(edit, dict):
        prompt_fallback = str(prompt_data.get("prompt") or "")
        negative_fallback = str(prompt_data.get("negative_prompt") or "")
        provider_payload_fallback = _format_provider_payload_json(prompt_data.get("provider_payload"))
        provider_payload_json = str(edit["provider_payload_json"]) if "provider_payload_json" in edit else provider_payload_fallback
        provider_payload, provider_payload_error = _parse_provider_payload_json(provider_payload_json)
        return {
            "prompt": str(edit["prompt"]) if "prompt" in edit else prompt_fallback,
            "negative_prompt": str(edit["negative_prompt"]) if "negative_prompt" in edit else negative_fallback,
            "provider_payload_json": provider_payload_json,
            "provider_payload": provider_payload,
            "provider_payload_error": provider_payload_error,
        }
    legacy_overrides = dict(st.session_state.get("image_prompt_overrides") or {})
    if rel_path in legacy_overrides:
        legacy = legacy_overrides.get(rel_path)
        return {
            "prompt": str(legacy) if legacy is not None else "",
            "negative_prompt": str(prompt_data.get("negative_prompt") or ""),
            "provider_payload_json": _format_provider_payload_json(prompt_data.get("provider_payload")),
            "provider_payload": dict(prompt_data.get("provider_payload") or {}),
            "provider_payload_error": "",
        }
    provider_payload_json = _format_provider_payload_json(prompt_data.get("provider_payload"))
    return {
        "prompt": str(prompt_data.get("prompt") or ""),
        "negative_prompt": str(prompt_data.get("negative_prompt") or ""),
        "provider_payload_json": provider_payload_json,
        "provider_payload": dict(prompt_data.get("provider_payload") or {}),
        "provider_payload_error": "",
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
        provider_payload = effective.get("provider_payload")
        if isinstance(provider_payload, dict) and provider_payload:
            payload[rel_path]["provider_payload"] = provider_payload
    return payload

