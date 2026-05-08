from __future__ import annotations

import time
from dataclasses import asdict
from hashlib import sha256
from typing import Any

from .client import LLMClient, LLMConfig

DEFAULT_TEST_SYSTEM_PROMPT = (
    "You are a connectivity test assistant. Reply briefly and clearly. "
    "When asked for JSON, return valid JSON only."
)
DEFAULT_TEST_USER_PROMPT = (
    'Return valid JSON only: {"status":"ok","message":"llm_test_passed"}'
)


def resolve_test_prompts(
    system_prompt: str | None = None,
    user_prompt: str | None = None,
) -> tuple[str, str]:
    resolved_system = (system_prompt or '').strip() or DEFAULT_TEST_SYSTEM_PROMPT
    resolved_user = (user_prompt or '').strip() or DEFAULT_TEST_USER_PROMPT
    return resolved_system, resolved_user


def llm_config_fingerprint(cfg: LLMConfig) -> str:
    payload = asdict(cfg).copy()
    payload["api_key"] = "***" if payload.get("api_key") else ""
    raw = repr(sorted(payload.items())).encode("utf-8")
    return sha256(raw).hexdigest()[:12]


def summarize_llm_status(
    *,
    current_cfg: LLMConfig,
    last_result: dict[str, Any] | None,
    last_error: str = "",
    last_cfg_fingerprint: str = "",
) -> dict[str, str]:
    current_fp = llm_config_fingerprint(current_cfg)
    if last_error and last_cfg_fingerprint == current_fp:
        return {"state": "error", "label": "LLM: lỗi kết nối", "detail": last_error}
    if last_result and last_cfg_fingerprint == current_fp:
        latency = last_result.get("latency_ms")
        detail = "Đã kiểm tra endpoint hiện tại"
        if latency is not None:
            detail += f" • {latency} ms"
        return {"state": "ok", "label": "LLM: sẵn sàng", "detail": detail}
    if last_result or last_error:
        return {"state": "stale", "label": "LLM: cần kiểm tra lại", "detail": "Cấu hình LLM đã thay đổi từ lần test trước."}
    return {"state": "unknown", "label": "LLM: chưa kiểm tra", "detail": "Chưa có kết quả Test LLM cho cấu hình hiện tại."}


def run_llm_smoke_test(
    cfg: LLMConfig,
    *,
    system_prompt: str = DEFAULT_TEST_SYSTEM_PROMPT,
    user_prompt: str = DEFAULT_TEST_USER_PROMPT,
) -> dict[str, Any]:
    """Run a lightweight test prompt against the configured chat-completions endpoint."""
    system_prompt, user_prompt = resolve_test_prompts(system_prompt, user_prompt)
    client = LLMClient(cfg)
    started = time.perf_counter()
    content = client.chat(system_prompt, user_prompt)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "latency_ms": elapsed_ms,
        "endpoint": client.url,
        "model": client.model,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "response_text": content,
    }
