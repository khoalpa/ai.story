from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import yaml

from story.audio_story_spec import (
    OUTLINE_KEYS,
    REQUIRED_META_KEYS,
    normalize_outline_key,
    render_plain_script,
    validate_canonical_authoring,
)
from story.client import LLMConfig, LLMResponseFormatError
from story.generate_script_config import ResolvedPaths, RuntimeContext
from story.generate_script_runner import (
    generate_authoring_with_retries,
    generate_chunked_authoring,
    generate_chunked_authoring_from_outline,
)
from story.gui.errors import StoryGenerationError, StoryLLMOutputError
from story.service import (
    LLMClient,
    build_meta_outline_prompt,
    extract_json,
    normalize_story_mode,
    sanitize_authoring_inplace,
    validate_authoring,
)

OUTLINE_FAST_RETRY_ATTEMPTS = 1
OUTLINE_JSON_PARSE_ATTEMPTS = 2


def _validate_outline_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed_root = {"meta", "outline", "script", "_auto_repair_log"}
    extra_root = sorted(set(payload.keys()) - allowed_root)
    if extra_root:
        errors.append(f"Root JSON có field không hợp lệ: {extra_root}.")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        errors.append("meta is not object")
    else:
        extra_meta = sorted(set(meta.keys()) - set(REQUIRED_META_KEYS))
        if extra_meta:
            errors.append(f"meta có field không hợp lệ: {extra_meta}.")
        missing_meta = [key for key in REQUIRED_META_KEYS if key not in meta]
        if missing_meta:
            errors.append(f"meta thiếu field bắt buộc: {missing_meta}.")
        for key in REQUIRED_META_KEYS:
            if key not in meta:
                continue
            value = meta.get(key)
            if key in ("length_min", "length_max"):
                if not isinstance(value, int):
                    errors.append(f"meta.{key} phải là integer.")
            elif key == "tags":
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    errors.append("meta.tags phải là array[string].")
            elif not isinstance(value, str):
                errors.append(f"meta.{key} phải là string.")
            elif key not in {"series", "episode"} and not value.strip():
                errors.append(f"meta.{key} phải là string không rỗng.")
        lang = str(meta.get("language", "")).strip().lower()
        if lang and lang not in {"vi", "en"}:
            errors.append("meta.language chỉ được là 'vi' hoặc 'en'.")

    outline = payload.get("outline")
    if not isinstance(outline, dict):
        errors.append("outline is not object")
    else:
        normalized_outline = {normalize_outline_key(key): value for key, value in outline.items()}
        extra_outline = sorted(set(normalized_outline.keys()) - set(OUTLINE_KEYS))
        if extra_outline:
            errors.append(f"outline có field không hợp lệ: {extra_outline}.")
        outline_keys = [normalize_outline_key(key) for key in outline.keys()]
        if tuple(outline_keys) != OUTLINE_KEYS:
            errors.append(f"outline phải có đúng 8 key theo thứ tự: {list(OUTLINE_KEYS)}.")
        for key in OUTLINE_KEYS:
            value = normalized_outline.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"outline.{key} phải là string không rỗng.")

    script = payload.get("script")
    if not isinstance(script, list):
        errors.append("script phải là array rỗng khi Generate outline.")
    elif script:
        errors.append("script phải rỗng khi Generate outline.")
    return errors


def _resolve_story_seed(settings: dict[str, Any]) -> int:
    try:
        seed = int(settings.get("story_seed") or 0)
    except (TypeError, ValueError):
        seed = 0
    return seed if seed > 0 else 1


def _brief_with_story_seed(brief: dict[str, Any], seed: int) -> dict[str, Any]:
    seeded = dict(brief)
    variation = dict(seeded.get("variation") or {})
    variation["seed"] = seed
    variation["instruction"] = (
        "Use this seed as a creative variation key. Keep the brief constraints, "
        "but choose different character details, scene beats, motifs, and phrasing for different seeds."
    )
    seeded["variation"] = variation
    return seeded


def _build_llm_config(settings: dict[str, Any]) -> LLMConfig:
    return LLMConfig(
        base_url=str(settings.get("base_url") or "").strip(),
        model=str(settings.get("model") or "").strip(),
        timeout_s=int(settings.get("timeout_s") or 120),
        max_tokens=int(settings.get("max_tokens") or 4096),
        temperature=float(settings.get("temperature") or 0.0),
        api_key=str(settings.get("api_key") or "not-needed"),
        retry_attempts=max(1, int(settings.get("retries") or 1)),
        local_update_target=str(settings.get("local_update_target") or "").strip(),
    )


def _build_outline_llm_config(cfg: LLMConfig) -> LLMConfig:
    return replace(
        cfg,
        max_tokens=cfg.max_tokens,
        retry_attempts=OUTLINE_FAST_RETRY_ATTEMPTS,
    )


def _build_runtime_context(
    *,
    brief: dict[str, Any],
    system_prompt: str,
    mode: str,
    llm_config: LLMConfig,
) -> RuntimeContext:
    duration_min = int((brief.get("goals") or {}).get("target_duration_min", 0) or 0)
    min_lines = duration_min * 12 if duration_min > 0 else 120
    return RuntimeContext(
        mode=mode,
        brief=brief,
        system_prompt=system_prompt,
        paths=ResolvedPaths(
            repo_root=Path.cwd(),
            brief_path=Path("<memory:brief>"),
            system_prompt_path=Path("<memory:system_prompt>"),
            output_base=Path("output/story"),
        ),
        llm_config=llm_config,
        min_lines=min_lines,
    )


def _raise_story_generation_error(authoring: dict[str, Any], message: str) -> None:
    try:
        failed_plain_script = render_plain_script(authoring)
    except (KeyError, TypeError, ValueError):
        failed_plain_script = ""
    raise StoryGenerationError(message, authoring=authoring, plain_script=failed_plain_script)


def build_story_run_context(*, brief_text: str, system_prompt: str, settings: dict[str, Any]) -> dict[str, Any]:
    brief = yaml.safe_load(brief_text) or {}
    if not isinstance(brief, dict):
        raise ValueError("Brief YAML must parse to an object at the root.")
    story_seed = _resolve_story_seed(settings)
    seeded_brief = _brief_with_story_seed(brief, story_seed)

    selected_mode = str(settings.get("mode") or "trend").strip()
    base_mode = normalize_story_mode(settings.get("base_mode") or selected_mode)
    llm_config = _build_llm_config(settings)
    context = _build_runtime_context(
        brief=seeded_brief,
        system_prompt=system_prompt,
        mode=base_mode,
        llm_config=llm_config,
    )
    return {
        "brief": brief,
        "story_seed": story_seed,
        "selected_mode": selected_mode,
        "base_mode": base_mode,
        "llm_config": llm_config,
        "context": context,
        "settings_summary": {
            "mode": selected_mode,
            "base_mode": base_mode,
            "chunked": bool(settings.get("chunked")),
            "chunk_size": int(settings.get("chunk_size") or 60),
            "max_tokens": int(settings.get("max_tokens") or 4096),
            "temperature": float(settings.get("temperature") or 0.0),
            "story_seed": story_seed,
        },
    }


def generate_story_outline(
    *,
    brief_text: str,
    system_prompt: str,
    settings: dict[str, Any],
    event_sink: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    run = build_story_run_context(brief_text=brief_text, system_prompt=system_prompt, settings=settings)
    context: RuntimeContext = run["context"]
    outline_llm_config = _build_outline_llm_config(run["llm_config"])
    client = LLMClient(outline_llm_config)
    if event_sink:
        event_sink("outline", f"Generating story outline (fast, max_tokens={outline_llm_config.max_tokens})")

    outline_prompt = build_meta_outline_prompt(context.brief, mode=context.mode)
    raw = ""
    last_error: Exception | None = None
    for attempt in range(1, OUTLINE_JSON_PARSE_ATTEMPTS + 1):
        prompt = outline_prompt
        if attempt > 1:
            prompt = (
                f"{outline_prompt}\n\n[RETRY NOTE]\n"
                "The previous response was not valid JSON. Return exactly one JSON object only, "
                "with double-quoted keys and string values, no markdown, no comments, no trailing commas."
            )
            if event_sink:
                event_sink("outline", f"Retrying story outline JSON parse ({attempt}/{OUTLINE_JSON_PARSE_ATTEMPTS})")
        try:
            raw = client.chat(context.system_prompt, prompt)
        except LLMResponseFormatError as exc:
            raise StoryLLMOutputError(
                "Outline LLM response was empty or malformed before JSON parsing. "
                "Check whether the local model emitted content, then retry with a slightly higher Max tokens if needed. "
                f"Details: {exc}",
                raw_response=raw,
            ) from exc
        try:
            outline_payload = extract_json(raw)
            break
        except Exception as exc:
            last_error = exc
    else:
        preview = " ".join(raw.split())[:600]
        raise StoryLLMOutputError(
            "Outline response is not valid JSON after retries. "
            "The model may have returned prose, markdown, or a truncated JSON object. "
            f"Details: {last_error}. preview={preview}",
            raw_response=raw,
        )
    if not isinstance(outline_payload, dict):
        raise ValueError("meta/outline response is not an object")
    sanitize_authoring_inplace(outline_payload)
    if not isinstance(outline_payload.get("meta") or {}, dict):
        raise ValueError("meta is not object")
    if not isinstance(outline_payload.get("outline") or {}, dict):
        raise ValueError("outline is not object")
    outline_errors = _validate_outline_payload(outline_payload)
    if outline_errors:
        raise ValueError("Outline payload không đúng contract: " + "; ".join(outline_errors))

    return {
        "brief": run["brief"],
        "outline_payload": outline_payload,
        "raw_outline_response": raw,
        "mode": run["selected_mode"],
        "base_mode": run["base_mode"],
        "mode_label": settings.get("mode_label") or run["selected_mode"],
        "settings_summary": {**run["settings_summary"], "outline_max_tokens": outline_llm_config.max_tokens},
        "story_seed": run["story_seed"],
    }


def generate_story_draft(
    *,
    brief_text: str,
    system_prompt: str,
    settings: dict[str, Any],
    outline_payload: dict[str, Any] | None = None,
    event_sink: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    run = build_story_run_context(brief_text=brief_text, system_prompt=system_prompt, settings=settings)
    context: RuntimeContext = run["context"]
    client = LLMClient(run["llm_config"])
    if event_sink:
        event_sink("generate", "Generating story draft")

    if settings.get("chunked") and outline_payload:
        authoring = generate_chunked_authoring_from_outline(
            client=client,
            context=context,
            outline_payload=outline_payload,
            chunk_size=int(settings.get("chunk_size") or 60),
        )
    elif settings.get("chunked"):
        authoring = generate_chunked_authoring(
            client=client,
            context=context,
            chunk_size=int(settings.get("chunk_size") or 60),
        )
    else:
        authoring = generate_authoring_with_retries(
            client=client,
            context=context,
            retries=int(settings.get("retries") or 2),
        )

    return {
        "brief": run["brief"],
        "authoring": authoring,
        "mode": run["selected_mode"],
        "base_mode": run["base_mode"],
        "mode_label": settings.get("mode_label") or run["selected_mode"],
        "settings_summary": run["settings_summary"],
        "story_seed": run["story_seed"],
    }


def validate_and_render_story_result(
    *,
    draft: dict[str, Any],
    settings: dict[str, Any],
    last_error: str | None = None,
) -> dict[str, Any]:
    authoring = draft.get("authoring") or {}
    if not isinstance(authoring, dict):
        raise ValueError("Story draft authoring must be an object")

    ok, msg = validate_authoring(authoring)
    if not ok:
        _raise_story_generation_error(authoring, msg)

    plain_script = render_plain_script(authoring)
    canonical_errors = validate_canonical_authoring(authoring)
    selected_mode = str(settings.get("mode") or "trend").strip()
    return {
        "brief": draft.get("brief") or {},
        "authoring": authoring,
        "plain_script": plain_script,
        "canonical_errors": canonical_errors,
        "mode": draft.get("mode") or selected_mode,
        "base_mode": draft.get("base_mode") or normalize_story_mode(settings.get("base_mode") or selected_mode),
        "mode_label": draft.get("mode_label") or settings.get("mode_label") or selected_mode,
        "last_error": last_error,
        "story_seed": draft.get("story_seed") or _resolve_story_seed(settings),
    }


def generate_story(
    *,
    brief_text: str,
    system_prompt: str,
    settings: dict[str, Any],
    event_sink: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    last_err = None
    try:
        if event_sink:
            event_sink("meta", "Loaded LLM configuration")
        outline = generate_story_outline(
            brief_text=brief_text,
            system_prompt=system_prompt,
            settings=settings,
            event_sink=event_sink,
        )
        draft = generate_story_draft(
            brief_text=brief_text,
            system_prompt=system_prompt,
            settings=settings,
            outline_payload=outline.get("outline_payload") if settings.get("chunked") else None,
            event_sink=event_sink,
        )
    except SystemExit as exc:
        last_err = str(exc)
        raise ValueError(last_err) from exc
    except (KeyError, TypeError, ValueError, RuntimeError, yaml.YAMLError) as exc:
        last_err = str(exc)
        raise

    return validate_and_render_story_result(draft=draft, settings=settings, last_error=last_err)
