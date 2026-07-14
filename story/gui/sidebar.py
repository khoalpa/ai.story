from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import streamlit as st

from story.gui.llm_test import _build_test_cfg, current_llm_status, current_test_prompts
from story.gui.presets import list_story_mode_ids, story_mode_base_mode, story_mode_label
from story.llm_provider_runtime import resolve_provider_switch
from story.llm_providers import clear_provider_preset_cache
from story.llm_provider_user_config import load_user_llm_settings, save_user_llm_settings, user_llm_settings_path
from story.testing import llm_config_fingerprint, run_llm_smoke_test
from story.llm_providers import (
    get_model_profile,
    get_provider_preset,
    infer_provider_id,
    list_model_profile_ids,
    list_provider_ids,
    model_profile_description,
    model_profile_label,
    provider_description,
    provider_label,
)
from story.paths import resolve_modes_root, resolve_project_root
from story.model_store import list_local_models, list_local_targets, provider_models_dir, provider_target_dir
from story.gui.provider_actions import ProviderAction, render_action_status, render_provider_action_row, set_action_status
from story.gui.sidebar_sections import SidebarSection
from story.gui.user_messages import render_user_message, GuidanceAction, UserMessage

SettingsDict = dict[str, Any]
DEFAULT_STORY_MODE = "trend"

PROVIDER_KEY = "story_llm_provider_id"
PROVIDER_LAST_KEY = "story_llm_provider_last"
PROFILE_KEY = "story_llm_profile_id"
PROFILE_LAST_KEY = "story_llm_profile_last"
BASE_URL_KEY = "story_llm_base_url_input"
MODEL_KEY = "story_llm_model_input"
API_KEY_KEY = "story_llm_api_key_input"
PERSISTENCE_STATUS_KEY = "story_llm_persistence_status"
PENDING_PROVIDER_APPLY_KEY = "_story_llm_pending_provider_apply"
STORY_SEED_KEY = "story_generation_seed"
DEFAULT_PROVIDER_ID = "lmdeploy"


def _randomize_story_seed() -> None:
    st.session_state[STORY_SEED_KEY] = random.randint(1, 2_147_483_647)


def _queue_provider_profile_defaults(
    provider_id: str,
    profile_id: str,
    *,
    overrides: dict[str, str] | None = None,
    status_message: str | None = None,
) -> None:
    st.session_state[PENDING_PROVIDER_APPLY_KEY] = {
        "provider_id": provider_id,
        "profile_id": profile_id,
        "overrides": overrides or {},
        "status_message": status_message or "",
    }


def _consume_pending_provider_profile_defaults() -> None:
    pending = st.session_state.pop(PENDING_PROVIDER_APPLY_KEY, None)
    if not pending:
        return
    provider_id = str(pending.get("provider_id") or DEFAULT_PROVIDER_ID)
    profile_id = str(pending.get("profile_id") or "")
    overrides = dict(pending.get("overrides") or {})
    defaults = resolve_provider_switch(provider_id, profile_id)
    st.session_state[PROVIDER_KEY] = defaults["llm_provider"]
    st.session_state[PROVIDER_LAST_KEY] = defaults["llm_provider"]
    st.session_state[PROFILE_KEY] = defaults["llm_profile"]
    st.session_state[PROFILE_LAST_KEY] = defaults["llm_profile"]
    st.session_state[BASE_URL_KEY] = str(overrides.get("base_url", defaults["base_url"]))
    st.session_state[MODEL_KEY] = str(overrides.get("model", defaults["model"]))
    st.session_state[API_KEY_KEY] = str(overrides.get("api_key", defaults["api_key"]))
    if pending.get("status_message"):
        st.session_state[PERSISTENCE_STATUS_KEY] = str(pending["status_message"])


def _on_provider_changed() -> None:
    provider_id = str(st.session_state.get(PROVIDER_KEY) or DEFAULT_PROVIDER_ID)
    provider = get_provider_preset(provider_id)
    _queue_provider_profile_defaults(provider_id, provider.default_profile_id)


def _on_profile_changed() -> None:
    provider_id = str(st.session_state.get(PROVIDER_KEY) or DEFAULT_PROVIDER_ID)
    profile_id = str(st.session_state.get(PROFILE_KEY) or "")
    _queue_provider_profile_defaults(provider_id, profile_id)

def _capture_current_provider_settings() -> dict[str, str]:
    return {
        "llm_provider": str(st.session_state.get(PROVIDER_KEY) or DEFAULT_PROVIDER_ID),
        "llm_profile": str(st.session_state.get(PROFILE_KEY) or ""),
        "base_url": str(st.session_state.get(BASE_URL_KEY) or "").strip(),
        "model": str(st.session_state.get(MODEL_KEY) or "").strip(),
        "api_key": str(st.session_state.get(API_KEY_KEY) or "").strip(),
    }


def _ensure_provider_state() -> None:
    inferred_provider = infer_provider_id(
        str(st.session_state.get(BASE_URL_KEY) or ""),
        str(st.session_state.get(API_KEY_KEY) or ""),
    )
    provider_id = str(st.session_state.get(PROVIDER_KEY) or inferred_provider or DEFAULT_PROVIDER_ID)
    preset = get_provider_preset(provider_id)
    profile_id = str(st.session_state.get(PROFILE_KEY) or preset.default_profile_id)
    profile = get_model_profile(provider_id, profile_id)
    defaults = resolve_provider_switch(provider_id, profile.profile_id)
    st.session_state.setdefault(PROVIDER_KEY, provider_id)
    st.session_state.setdefault(PROVIDER_LAST_KEY, provider_id)
    st.session_state.setdefault(PROFILE_KEY, profile.profile_id)
    st.session_state.setdefault(PROFILE_LAST_KEY, profile.profile_id)
    st.session_state.setdefault(BASE_URL_KEY, defaults["base_url"])
    st.session_state.setdefault(MODEL_KEY, defaults["model"])
    st.session_state.setdefault(API_KEY_KEY, defaults["api_key"])


def _normalize_provider_profile_state() -> tuple[str, str]:
    provider_id = str(st.session_state.get(PROVIDER_KEY) or DEFAULT_PROVIDER_ID)
    preset = get_provider_preset(provider_id)
    profile_ids = list_model_profile_ids(provider_id)
    profile_id = str(st.session_state.get(PROFILE_KEY) or preset.default_profile_id)
    if profile_id not in profile_ids:
        profile_id = preset.default_profile_id
        st.session_state[PROFILE_KEY] = profile_id
        st.session_state[PROFILE_LAST_KEY] = profile_id
    return provider_id, profile_id


def _restore_saved_provider_settings() -> str:
    loaded = load_user_llm_settings()
    if not loaded:
        return f"No saved configuration found at {user_llm_settings_path()}"
    _queue_provider_profile_defaults(
        loaded["llm_provider"],
        loaded["llm_profile"],
        overrides={
            "base_url": loaded["base_url"],
            "model": loaded["model"],
            "api_key": loaded["api_key"],
        },
        status_message=f"Restored provider/profile from {user_llm_settings_path()}",
    )
    return f"Restoring provider/profile from {user_llm_settings_path()}"


def _persist_current_provider_settings() -> str:
    path = save_user_llm_settings(_capture_current_provider_settings())
    return f"Saved provider/profile configuration to {path}"




def _render_story_local_model_picker(*, provider_id: str, current_model: str) -> tuple[str, str, str]:
    target_dir = provider_target_dir("story", provider_id, __file__)
    local_targets = list_local_targets("story", __file__, provider_id=provider_id, max_depth=3)
    options = ["(manual)", *local_targets]
    key = f"story_local_model_target::{provider_id}"
    current_model = str(current_model or "").strip()
    default_scanned_target = local_targets[0] if local_targets else ""
    selected = str(st.session_state.get(key) or "(manual)")
    if selected == "(manual)" and current_model in {"", "auto"} and default_scanned_target:
        selected = default_scanned_target
    if current_model and current_model in local_targets:
        selected = current_model
    if selected not in options:
        selected = "(manual)"
    selected = st.selectbox("Local model target", options=options, index=options.index(selected), key=key, help="Scans story/models/<provider>/ directly. Choose a local target when the model is already placed in the project.")
    st.caption(f"Update target: {target_dir}")
    if local_targets:
        st.caption(f"Scanned local targets: {', '.join(local_targets[:6])}{' …' if len(local_targets) > 6 else ''}")
    if selected != "(manual)":
        st.session_state[MODEL_KEY] = selected
    manual_value = st.text_input("Model", value="" if selected != "(manual)" else current_model, key=MODEL_KEY)
    local_update_target = selected if selected != "(manual)" else ""
    return (selected if selected != "(manual)" else str(manual_value).strip()), str(target_dir), local_update_target

def _render_story_provider_actions(*, provider_id: str, profile_id: str, base_url: str, model: str, story_update_target: str, api_key: str, timeout_s: int, max_tokens: int, temperature: float, retries: int) -> None:
    status_key = "story_provider_action_status"

    def _refresh() -> None:
        clear_provider_preset_cache()
        local_models = list_local_models("story", __file__)
        models_dir = provider_models_dir("story", __file__)
        set_action_status(status_key, "success", f"Story: refreshed provider {provider_label(provider_id)} - models dir={models_dir} - local assets={len(local_models)}")

    def _test() -> None:
        try:
            cfg = _build_test_cfg({
                "base_url": base_url,
                "model": model,
                "local_update_target": story_update_target,
                "api_key": api_key,
                "timeout_s": timeout_s,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "retries": retries,
            })
            system_prompt, user_prompt = current_test_prompts()
            result = run_llm_smoke_test(cfg, system_prompt=system_prompt, user_prompt=user_prompt)
            st.session_state.story_llm_test_result = result
            st.session_state.story_llm_test_error = ""
            st.session_state.story_llm_test_cfg_fingerprint = llm_config_fingerprint(cfg)
            set_action_status(status_key, "success", f"Story: test {provider_label(provider_id)} OK - latency={result.get('latency_ms')} ms")
        except Exception as exc:
            st.session_state.story_llm_test_result = None
            st.session_state.story_llm_test_error = str(exc)
            st.session_state.story_llm_test_cfg_fingerprint = llm_config_fingerprint(cfg)
            set_action_status(status_key, "error", f"Story: test {provider_label(provider_id)} failed ({exc.__class__.__name__}: {exc})")

    def _update() -> None:
        target_dir = provider_target_dir("story", provider_id, __file__)
        set_action_status(status_key, "success", f"Story: Current update target = {target_dir}. For remote providers, place local model/config files here or update them from the external runtime/provider. Current provider: {provider_label(provider_id)} / {profile_id}")

    render_provider_action_row([
        ProviderAction("refresh", "Refresh", key=f"story_provider_refresh::{provider_id}", callback=_refresh),
        ProviderAction("test", "Test", key=f"story_provider_test::{provider_id}", callback=_test),
        ProviderAction("update", "Update", key=f"story_provider_update::{provider_id}", callback=_update),
    ])
    render_action_status(status_key)

def render_settings_sidebar() -> SettingsDict:
    project_root = resolve_project_root(Path.cwd())
    _ensure_provider_state()
    _consume_pending_provider_profile_defaults()
    provider_id, profile_id = _normalize_provider_profile_state()

    with st.sidebar:
        st.header(SidebarSection.PROFILES)
        modes_root_default = resolve_modes_root(project_root)
        modes_root = st.text_input("Modes root", value=str(modes_root_default))
        resolved_modes_root = Path(modes_root).expanduser()
        story_modes = list_story_mode_ids(project_root=project_root, modes_root=resolved_modes_root)
        default_mode = DEFAULT_STORY_MODE if DEFAULT_STORY_MODE in story_modes else story_modes[0]
        default_index = story_modes.index(default_mode)
        mode = st.selectbox(
            "Modes preset",
            story_modes,
            index=default_index,
            format_func=lambda mode_id: f"{story_mode_label(mode_id, project_root=project_root)} ({story_mode_base_mode(mode_id, project_root=project_root)})",
            help="Preset mode selects the suggested brief/prompt pair. Base mode is the core story type used by the generation engine.",
        )
        base_mode = story_mode_base_mode(mode, project_root=project_root)
        st.caption(f"Selected preset: {story_mode_label(mode, project_root=project_root)} - Base mode: {base_mode}")

        st.header(SidebarSection.PROVIDER)
        provider_ids = list_provider_ids()
        provider_id = st.selectbox(
            "LLM provider",
            provider_ids,
            key=PROVIDER_KEY,
            format_func=provider_label,
            help="Choose a provider so the app can suggest matching base URL, model, and default API key settings.",
            on_change=_on_provider_changed,
        )
        provider = get_provider_preset(provider_id)

        profile_ids = list_model_profile_ids(provider_id)
        if profile_id not in profile_ids:
            profile_id = provider.default_profile_id
        profile_id = st.selectbox(
            "Model profile",
            profile_ids,
            key=PROFILE_KEY,
            format_func=lambda item: model_profile_label(provider_id, item),
            help="Profiles group base URL, model, and API key defaults for each provider.",
            on_change=_on_profile_changed,
        )

        preset = get_provider_preset(provider_id)
        profile = get_model_profile(provider_id, profile_id)
        st.caption(provider_description(provider_id))
        st.caption(f"Profile: {profile.label} - {model_profile_description(provider_id, profile_id)}")
        st.caption(f"Models dir: {provider_models_dir('story', __file__)}")
        if st.button("Reset theo profile hiện tại", width="stretch"):
            _queue_provider_profile_defaults(provider_id, profile_id)
            st.rerun()

        with st.expander("Cấu hình LLM đã lưu", expanded=False):
            persistence_cols = st.columns(2)
            if persistence_cols[0].button("Lưu cấu hình LLM", width="stretch"):
                st.session_state[PERSISTENCE_STATUS_KEY] = _persist_current_provider_settings()
                st.rerun()
            if persistence_cols[1].button("Khôi phục cấu hình LLM", width="stretch"):
                st.session_state[PERSISTENCE_STATUS_KEY] = _restore_saved_provider_settings()
                st.rerun()
            if st.session_state.get(PERSISTENCE_STATUS_KEY):
                st.info(str(st.session_state.get(PERSISTENCE_STATUS_KEY)))

        base_url = st.text_input("LLM base URL", key=BASE_URL_KEY)
        model, story_update_target, local_update_target = _render_story_local_model_picker(provider_id=provider_id, current_model=str(st.session_state.get(MODEL_KEY) or "").strip())
        api_key = st.text_input(
            "API key",
            key=API_KEY_KEY,
            type="password",
            help="Local LM Studio usually does not need an API key. Remote providers such as OpenAI require a valid API key.",
        )
        if preset.requires_api_key and not str(api_key or "").strip():
            render_user_message(UserMessage(level="warning", title="Missing API key", body="This provider needs an API key to run remote requests.", actions=(GuidanceAction("Enter an API key in the sidebar before running remote requests."), GuidanceAction("Use Test or Refresh to check again after updating."))))

        with st.expander(SidebarSection.GENERATION, expanded=True):
            if STORY_SEED_KEY not in st.session_state:
                st.session_state[STORY_SEED_KEY] = random.randint(1, 2_147_483_647)
            output_base = st.text_input(
                "Output base path",
                value="output/story/story",
                help="Base path used when saving Story outputs. The GUI writes .txt and .json beside this base path.",
            )
            seed_cols = st.columns([2, 1])
            story_seed = seed_cols[0].number_input("Story seed", min_value=1, max_value=2_147_483_647, step=1, key=STORY_SEED_KEY)
            seed_cols[1].button("Random seed", width="stretch", on_click=_randomize_story_seed)
            timeout_s = st.number_input("Timeout (s)", min_value=10, value=360, step=10)
            max_tokens = st.number_input("Max tokens", min_value=256, value=32768, step=256)
            temperature = st.slider("Temperature", min_value=0.0, max_value=1.5, value=0.7, step=0.1)
            retries = st.slider("Retries", 0, 5, 2)
            chunk_size = st.slider("Chunk size", 8, 120, 60)
            chunked = st.checkbox("Chunked generation", value=True)
            min_lines_override = st.number_input(
                "Min script lines",
                min_value=0,
                value=0,
                step=10,
                help="0 uses target_duration_min from the brief. Set a value to override the generated script length target.",
            )
            validate_generated_output = st.checkbox("Validate generated output", value=True)

        _render_story_provider_actions(
            provider_id=provider_id,
            profile_id=profile_id,
            base_url=base_url,
            model=model,
            story_update_target=local_update_target,
            api_key=api_key,
            timeout_s=int(timeout_s),
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            retries=int(retries),
        )

        preview_settings = {
            "base_url": base_url,
            "model": model,
            "local_update_target": local_update_target,
            "local_update_target_dir": story_update_target,
            "api_key": api_key,
            "timeout_s": int(timeout_s),
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "story_seed": int(story_seed),
            "retries": int(retries),
        }
        status = current_llm_status(preview_settings)
        badge = {"ok": "[OK]", "error": "[ERROR]", "stale": "[STALE]", "unknown": "[UNKNOWN]"}.get(status["state"], "[UNKNOWN]")
        st.caption(f"{badge} {status['label']} - {status['detail']}")
        test_before_generate = st.checkbox(
            "Test LLM before Generate",
            key="story_test_before_generate",
            help="Run a short smoke test against the current endpoint before calling the generation pipeline.",
        )
    return {
        "llm_provider": provider_id,
        "llm_provider_label": preset.label,
        "llm_profile": profile.profile_id,
        "llm_profile_label": profile.label,
        "base_url": base_url,
        "model": model,
        "local_update_target": local_update_target,
        "local_update_target_dir": story_update_target,
        "api_key": api_key,
        "output_base": output_base,
        "timeout_s": int(timeout_s),
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "story_seed": int(story_seed),
        "mode": mode,
        "base_mode": base_mode,
        "mode_label": story_mode_label(mode, project_root=project_root),
        "chunked": chunked,
        "chunk_size": int(chunk_size),
        "min_lines": int(min_lines_override),
        "retries": int(retries),
        "validate_generated_output": validate_generated_output,
        "test_before_generate": bool(test_before_generate),
        "project_root": str(project_root),
        "modes_root": str(resolved_modes_root),
    }


def render_sidebar() -> SettingsDict:
    return render_settings_sidebar()
