from __future__ import annotations

import subprocess
import sys
from textwrap import dedent
from typing import Any

from .audio_story_spec import ALLOWED_SCRIPT_ZONES
from .audio_story_spec import render_plain_script as spec_render_plain_script
from .service import (
    LLMClient,
    build_default_zone_counts,
    build_meta_outline_prompt,
    build_user_prompt,
    build_zone_chunk_prompt,
    dedupe_script_items,
    eprint,
    extract_json,
    extract_json_array,
    force_single_sentence_items_inplace,
    ensure_script_zone_order_inplace,
    normalize_chunk_items_to_single_sentence,
    post_process_authoring as service_post_process_authoring,
    sanitize_authoring_inplace,
    validate_authoring,
    write_json,
    write_text,
)
from .generate_script_config import RuntimeContext


def log_runtime_context(context: RuntimeContext) -> None:
    print(f"[INFO] Mode: {context.mode}")
    print(f"[INFO] System prompt: {context.paths.system_prompt_path}")
    print(f"[INFO] Loaded brief.yml: {context.paths.brief_path}")
    print(
        "[INFO] LLM base_url={base_url} model={model} timeout={timeout}s max_tokens={max_tokens} temperature={temperature}".format(
            base_url=context.llm_config.base_url,
            model=context.llm_config.model,
            timeout=context.llm_config.timeout_s,
            max_tokens=context.llm_config.max_tokens,
            temperature=context.llm_config.temperature,
        )
    )


def _post_process_authoring(authoring: dict[str, Any]) -> dict[str, Any]:
    authoring = service_post_process_authoring(authoring)
    force_single_sentence_items_inplace(authoring)
    ensure_script_zone_order_inplace(authoring)
    ok, msg = validate_authoring(authoring)
    if not ok:
        raise ValueError(msg)
    return authoring


def generate_chunked_authoring(*, client: LLMClient, context: RuntimeContext, chunk_size: int) -> dict[str, Any]:
    meta_outline_prompt = build_meta_outline_prompt(context.brief, mode=context.mode)
    raw0 = client.chat(context.system_prompt, meta_outline_prompt)
    obj0 = extract_json(raw0)
    sanitize_authoring_inplace(obj0)
    return generate_chunked_authoring_from_outline(
        client=client,
        context=context,
        outline_payload=obj0,
        chunk_size=chunk_size,
    )

def generate_chunked_authoring_from_outline(
    *,
    client: LLMClient,
    context: RuntimeContext,
    outline_payload: dict[str, Any],
    chunk_size: int,
) -> dict[str, Any]:
    if not isinstance(outline_payload, dict):
        raise ValueError("meta/outline response is not an object")

    meta = outline_payload.get("meta") or {}
    outline = outline_payload.get("outline") or {}
    if not isinstance(meta, dict):
        raise ValueError("meta is not object")
    if not isinstance(outline, dict):
        raise ValueError("outline is not object")

    language_primary = str((context.brief.get("project") or {}).get("language_primary", "VI")).strip().upper()
    lang_tag = "VI" if language_primary.startswith("VI") else "EN"
    zone_counts = build_default_zone_counts(context.min_lines)
    script_items: list[dict[str, Any]] = []

    for zone in ALLOWED_SCRIPT_ZONES:
        needed = int(zone_counts.get(zone, 0))
        speed = "SLOW" if zone in ("LỜI CHÀO", "KẾT TRUYỆN", "TẠM BIỆT") else "NORMAL"

        while needed > 0:
            take = min(chunk_size, needed)
            user_prompt = build_zone_chunk_prompt(meta, outline, zone, take, lang_tag=lang_tag, speed=speed, mode=context.mode)
            chunk_items = _generate_chunk_items(
                client=client,
                system_prompt=context.system_prompt,
                user_prompt=user_prompt,
                zone=zone,
                speed=speed,
                take=take,
                lang_tag=lang_tag,
            )
            script_items.extend(chunk_items)
            needed -= len(chunk_items)

    return _post_process_authoring({"meta": meta, "outline": outline, "script": script_items})


def _generate_chunk_items(*, client: LLMClient, system_prompt: str, user_prompt: str, zone: str, speed: str, take: int, lang_tag: str) -> list[dict[str, Any]]:
    last_error: str | None = None
    for _attempt in range(1, 4):
        try:
            prompt = user_prompt
            if _attempt > 1:
                prompt = f"{user_prompt}\n\n[RETRY NOTE]\nLần trước model không trả về JSON array hợp lệ. Hãy trả về DUY NHẤT một JSON ARRAY hợp lệ, không markdown, không giải thích, không object bọc ngoài."
            raw_chunk = client.chat(system_prompt, prompt)
            parsed = extract_json_array(raw_chunk)
            chunk_items = normalize_chunk_items_to_single_sentence(parsed, zone, speed, lang_tag)
            chunk_items = dedupe_script_items(
                chunk_items,
                exact_window=0,
                near_window=max(6, min(12, take)),
                similarity_threshold=0.88,
                max_occurrences_per_signature=1,
            )
            if not chunk_items:
                raise ValueError("empty usable array after normalization/dedupe")
            return chunk_items[:take]
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            last_error = str(exc)
    raise ValueError(f"chunk for zone {zone} failed to produce usable JSON array: {last_error}")


def generate_authoring_with_retries(*, client: LLMClient, context: RuntimeContext, retries: int) -> dict[str, Any]:
    user_prompt = build_user_prompt(context.brief, mode=context.mode)
    last_error: str | None = None

    for attempt in range(1, retries + 2):
        try:
            raw = client.chat(context.system_prompt, user_prompt)
            authoring = extract_json(raw)
            if not isinstance(authoring, dict):
                raise ValueError("LLM response is not a JSON object")
            return _post_process_authoring(authoring)
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            last_error = str(exc)
            eprint(f"[WARN] Attempt {attempt} failed: {last_error}")
            user_prompt = user_prompt + dedent(f"""

            [RETRY NOTE]
            Lỗi trước đó: {last_error}
            Hãy sửa và trả về JSON hợp lệ.
            NHẮC LẠI: script phải có >= {context.min_lines} items.
            Mỗi script item chỉ được chứa đúng 1 câu.
            Nếu một text có 2 câu, hãy tách thành 2 item riêng.
            Không lặp lại nguyên câu cũ hoặc câu gần giống nhau quá mức.
            Tránh lặp motif/ý tương tự nhiều lần liên tiếp trong cùng một zone.
            """).strip()

    raise SystemExit(f"[ERROR] Failed to generate valid authoring JSON after retries. Last error: {last_error}")


def write_outputs(authoring: dict[str, Any], context: RuntimeContext) -> tuple[str, str]:
    txt_path = context.paths.output_base.with_suffix(".txt")
    json_path = context.paths.output_base.with_suffix(".json")
    plain = spec_render_plain_script(authoring)
    write_text(txt_path, plain)
    write_json(json_path, authoring)
    print(f"[INFO] Wrote plain script: {txt_path}")
    print(f"[INFO] Wrote authoring JSON: {json_path}")
    return str(txt_path), str(json_path)


def run_plain_script_validation(context: RuntimeContext) -> None:
    validate_py = context.paths.repo_root / "validate_plain_script.py"
    if not validate_py.exists():
        eprint(f"[WARN] validate_plain_script.py not found at {validate_py}. Skipping.")
        return

    txt_path = context.paths.output_base.with_suffix(".txt")
    print("=" * 60)
    print(f"VALIDATE SCRIPT: {txt_path}")
    print("=" * 60)
    result = subprocess.run([sys.executable, str(validate_py), "-i", str(txt_path), "--json"], text=True)
    if result.returncode != 0:
        raise SystemExit("[ERROR] validate_plain_script.py: FAILED")
    print("[INFO] validate_plain_script.py: OK")
