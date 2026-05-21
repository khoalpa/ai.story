from __future__ import annotations

__test__ = False

from typing import Any

import streamlit as st

from story.client import LLMConfig
from story.testing import (
    DEFAULT_TEST_SYSTEM_PROMPT,
    DEFAULT_TEST_USER_PROMPT,
    llm_config_fingerprint,
    resolve_test_prompts,
    run_llm_smoke_test,
    summarize_llm_status,
)
from story.gui.errors import format_runtime_error
from story.llm_provider_runtime import run_provider_quick_test
from story.llm_providers import list_provider_ids, provider_label
from story.gui.user_messages import UserMessage, render_user_message, show_provider_error

DEFAULT_GUI_TEST_USER_PROMPT = DEFAULT_TEST_USER_PROMPT
SYSTEM_INPUT_KEY = "story_llm_test_system_prompt_input"
USER_INPUT_KEY = "story_llm_test_user_prompt_input"
SYSTEM_STATE_KEY = "story_llm_test_system_prompt"
USER_STATE_KEY = "story_llm_test_user_prompt"
RESET_FLAG_KEY = "story_llm_test_reset_pending"
QUICK_RESULT_KEY = "story_llm_quick_test_result"
QUICK_ERROR_KEY = "story_llm_quick_test_error"


def _apply_prompt_input_defaults() -> None:
    if st.session_state.get(RESET_FLAG_KEY):
        st.session_state[SYSTEM_INPUT_KEY] = DEFAULT_TEST_SYSTEM_PROMPT
        st.session_state[USER_INPUT_KEY] = DEFAULT_GUI_TEST_USER_PROMPT
        st.session_state[SYSTEM_STATE_KEY] = DEFAULT_TEST_SYSTEM_PROMPT
        st.session_state[USER_STATE_KEY] = DEFAULT_GUI_TEST_USER_PROMPT
        st.session_state[RESET_FLAG_KEY] = False
        return
    current_system = str(st.session_state.get(SYSTEM_INPUT_KEY) or st.session_state.get(SYSTEM_STATE_KEY) or "")
    current_user = str(st.session_state.get(USER_INPUT_KEY) or st.session_state.get(USER_STATE_KEY) or "")
    resolved_system, resolved_user = resolve_test_prompts(current_system, current_user)
    st.session_state.setdefault(SYSTEM_INPUT_KEY, resolved_system)
    st.session_state.setdefault(USER_INPUT_KEY, resolved_user)
    st.session_state.setdefault(SYSTEM_STATE_KEY, resolved_system)
    st.session_state.setdefault(USER_STATE_KEY, resolved_user)


def current_test_prompts() -> tuple[str, str]:
    return resolve_test_prompts(
        str(st.session_state.get(SYSTEM_INPUT_KEY) or st.session_state.get(SYSTEM_STATE_KEY) or ""),
        str(st.session_state.get(USER_INPUT_KEY) or st.session_state.get(USER_STATE_KEY) or ""),
    )


def _build_test_cfg(settings: dict[str, Any]) -> LLMConfig:
    return LLMConfig(
        base_url=str(settings.get("base_url") or "").strip(),
        model=str(settings.get("model") or "").strip(),
        timeout_s=int(settings.get("timeout_s") or 120),
        max_tokens=int(settings.get("max_tokens") or 256),
        temperature=float(settings.get("temperature") or 0.0),
        api_key=str(settings.get("api_key") or "not-needed"),
        retry_attempts=max(1, int(settings.get("retries") or 1)),
        local_update_target=str(settings.get("local_update_target") or "").strip(),
    )


def current_llm_status(settings: dict[str, Any]) -> dict[str, str]:
    cfg = _build_test_cfg(settings)
    return summarize_llm_status(
        current_cfg=cfg,
        last_result=st.session_state.get("story_llm_test_result"),
        last_error=str(st.session_state.get("story_llm_test_error") or ""),
        last_cfg_fingerprint=str(st.session_state.get("story_llm_test_cfg_fingerprint") or ""),
    )


def _render_quick_test_feedback() -> None:
    quick_error = str(st.session_state.get(QUICK_ERROR_KEY) or "")
    quick_result = st.session_state.get(QUICK_RESULT_KEY)
    if quick_error:
        show_provider_error(
            "LLM quick test",
            problem=quick_error,
            actions=[
                "Check the provider configuration in the sidebar.",
                "Run the quick test again after updating the model or endpoint.",
            ],
        )
    if quick_result:
        render_user_message(
            UserMessage(
                level="info",
                title="LLM quick test",
                body="Quick test succeeded - provider={provider} - profile={profile} - latency={latency} ms".format(
                    provider=quick_result.get("provider_label"),
                    profile=quick_result.get("profile_label"),
                    latency=quick_result.get("latency_ms"),
                ),
            )
        )


def render_provider_quick_tests(*, timeout_s: int = 30, max_tokens: int = 256) -> None:
    with st.expander("Quick test by provider", expanded=False):
        provider_ids = list_provider_ids()
        cols = st.columns(len(provider_ids))
        system_prompt, user_prompt = current_test_prompts()
        for idx, provider_id in enumerate(provider_ids):
            label = provider_label(provider_id)
            if cols[idx].button(f"{label}", key=f"quick_test_{provider_id}", width="stretch"):
                try:
                    result = run_provider_quick_test(
                        provider_id,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        timeout_s=int(timeout_s),
                        max_tokens=int(max_tokens),
                    )
                    st.session_state[QUICK_RESULT_KEY] = result
                    st.session_state[QUICK_ERROR_KEY] = ""
                except Exception as exc:
                    st.session_state[QUICK_RESULT_KEY] = None
                    st.session_state[QUICK_ERROR_KEY] = f"{label}: {format_runtime_error(exc)}"
                st.rerun()
        _render_quick_test_feedback()


def render_llm_test_panel(settings: dict[str, Any]) -> None:
    st.subheader("Test LLM")
    st.caption("Quickly check the OpenAI-compatible endpoint connection and response before running the generation pipeline.")

    _apply_prompt_input_defaults()

    system_prompt = st.text_area("Test system prompt", key=SYSTEM_INPUT_KEY, height=90)
    user_prompt = st.text_area("Test user prompt", key=USER_INPUT_KEY, height=110)

    cols = st.columns([1, 1, 3])
    if cols[0].button("Run Test LLM", width="stretch"):
        cfg = _build_test_cfg(settings)
        try:
            resolved_system_prompt, resolved_user_prompt = resolve_test_prompts(system_prompt, user_prompt)
            st.session_state[SYSTEM_STATE_KEY] = resolved_system_prompt
            st.session_state[USER_STATE_KEY] = resolved_user_prompt
            result = run_llm_smoke_test(cfg, system_prompt=resolved_system_prompt, user_prompt=resolved_user_prompt)
            st.session_state.story_llm_test_result = result
            st.session_state.story_llm_test_error = ""
            st.session_state.story_llm_test_cfg_fingerprint = llm_config_fingerprint(cfg)
        except Exception as exc:
            st.session_state.story_llm_test_result = None
            st.session_state.story_llm_test_error = format_runtime_error(exc)
            st.session_state.story_llm_test_cfg_fingerprint = llm_config_fingerprint(cfg)

    if cols[1].button("Reset test prompt", width="stretch"):
        st.session_state[RESET_FLAG_KEY] = True
        st.session_state.story_llm_test_result = None
        st.session_state.story_llm_test_error = ""
        st.session_state.story_llm_test_cfg_fingerprint = ""
        st.rerun()

    status = current_llm_status(settings)
    badge = {"ok": "[OK]", "error": "[ERROR]", "stale": "[STALE]", "unknown": "[UNKNOWN]"}.get(status["state"], "[UNKNOWN]")
    st.caption(f"{badge} {status['label']} - {status['detail']}")

    error_text = st.session_state.get("story_llm_test_error") or ""
    result = st.session_state.get("story_llm_test_result")

    if error_text:
        show_provider_error(
            "LLM test",
            problem=error_text,
            actions=[
                "Check the model, base URL, API key, and timeout.",
                "Use Run Test LLM after updating the configuration.",
            ],
        )
    if result:
        st.success(
            "Connection succeeded - model={model} - latency={latency} ms".format(
                model=result.get("model"),
                latency=result.get("latency_ms"),
            )
        )
        with st.expander("Test LLM response details", expanded=True):
            st.json(
                {
                    "endpoint": result.get("endpoint"),
                    "model": result.get("model"),
                    "latency_ms": result.get("latency_ms"),
                    "response_text": result.get("response_text"),
                }
            )
