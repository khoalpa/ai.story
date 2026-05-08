from __future__ import annotations

import argparse
import json
import os
import sys

from story.client import LLMConfig
from story.llm_providers import build_provider_settings, get_model_profile, list_model_profile_ids, list_provider_ids
from story.testing import (
    DEFAULT_TEST_SYSTEM_PROMPT,
    DEFAULT_TEST_USER_PROMPT,
    run_llm_smoke_test,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a lightweight LLM connectivity and response test.")
    parser.add_argument("--provider", choices=list_provider_ids(), default=os.getenv("LLM_PROVIDER", "lm_studio"))
    parser.add_argument("--profile", default=None, help="Model profile ID defined for the selected provider")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout-s", type=int, default=int(os.getenv("OPENAI_TIMEOUT_S", "30")))
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--system-prompt", default=DEFAULT_TEST_SYSTEM_PROMPT)
    parser.add_argument("--user-prompt", default=DEFAULT_TEST_USER_PROMPT)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    provider_defaults = build_provider_settings(ns.provider, ns.profile)
    selected_profile = get_model_profile(ns.provider, ns.profile)
    base_url = ns.base_url or provider_defaults["base_url"]
    model = ns.model or provider_defaults["model"]
    api_key = ns.api_key if ns.api_key is not None else provider_defaults["api_key"]
    cfg = LLMConfig(
        base_url=base_url,
        model=model,
        timeout_s=ns.timeout_s,
        max_tokens=ns.max_tokens,
        temperature=ns.temperature,
        api_key=api_key or "not-needed",
    )
    try:
        result = run_llm_smoke_test(cfg, system_prompt=ns.system_prompt, user_prompt=ns.user_prompt)
    except Exception as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "provider": ns.provider,
            "profile": selected_profile.profile_id,
            "base_url": base_url,
            "model": model,
        }
        if ns.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"[FAIL] LLM test failed: {exc}", file=sys.stderr)
        return 1

    result["provider"] = ns.provider
    result["profile"] = selected_profile.profile_id
    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[OK] LLM test passed • provider={ns.provider} • profile={selected_profile.profile_id} • model={result['model']} • latency={result['latency_ms']} ms")
        print(result["response_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
