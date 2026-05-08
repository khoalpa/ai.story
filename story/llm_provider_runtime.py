from __future__ import annotations

from typing import Any, Callable

from story.client import LLMConfig
from story.llm_providers import build_provider_settings, get_model_profile, get_provider_preset
from story.testing import run_llm_smoke_test


RunnerFn = Callable[..., dict[str, Any]]


def resolve_provider_switch(provider_id: str | None, profile_id: str | None = None) -> dict[str, str]:
    provider = get_provider_preset(provider_id)
    profile = get_model_profile(provider.provider_id, profile_id or provider.default_profile_id)
    return build_provider_settings(provider.provider_id, profile.profile_id)


def build_quick_test_config(
    provider_id: str | None,
    profile_id: str | None = None,
    *,
    timeout_s: int = 30,
    max_tokens: int = 256,
    temperature: float = 0.0,
) -> tuple[dict[str, str], LLMConfig]:
    defaults = resolve_provider_switch(provider_id, profile_id)
    cfg = LLMConfig(
        base_url=defaults["base_url"],
        model=defaults["model"],
        timeout_s=max(1, int(timeout_s)),
        max_tokens=max(1, int(max_tokens)),
        temperature=float(temperature),
        api_key=defaults["api_key"] or "not-needed",
        retry_attempts=1,
        local_update_target="",
    )
    return defaults, cfg


def run_provider_quick_test(
    provider_id: str | None,
    profile_id: str | None = None,
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int = 30,
    max_tokens: int = 256,
    temperature: float = 0.0,
    runner: RunnerFn = run_llm_smoke_test,
) -> dict[str, Any]:
    defaults, cfg = build_quick_test_config(
        provider_id,
        profile_id,
        timeout_s=timeout_s,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    result = runner(cfg, system_prompt=system_prompt, user_prompt=user_prompt)
    result.update(
        {
            "provider_id": defaults["llm_provider"],
            "provider_label": defaults["llm_provider_label"],
            "profile_id": defaults["llm_profile"],
            "profile_label": defaults["llm_profile_label"],
        }
    )
    return result
