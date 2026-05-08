from __future__ import annotations

from pathlib import Path

from story.paths import resolve_project_root

from .audio_story_spec import ALLOWED_SCRIPT_ZONES
from .audio_story_spec import render_plain_script as spec_render_plain_script
from .service import (
    LLMClient,
    LLMConfig,
    build_default_zone_counts,
    build_meta_outline_prompt,
    build_user_prompt,
    build_zone_chunk_prompt,
    dedupe_authoring_script_inplace,
    dedupe_script_items,
    default_brief_filename_for_mode,
    default_prompt_filename_for_mode,
    env_float,
    env_int,
    eprint,
    extract_json,
    extract_json_array,
    force_single_sentence_items_inplace,
    load_yaml,
    normalize_chunk_items_to_single_sentence,
    normalize_output_base,
    normalize_story_mode,
    prune_outline_echoes_inplace,
    prune_story_drift_inplace,
    prune_zone_misplaced_boilerplate_inplace,
    read_text,
    repair_authoring_single_sentence_inplace,
    sanitize_authoring_inplace,
    semantic_motif_cap_inplace,
    validate_authoring,
    write_json,
    write_text,
)
from .generate_script_args import build_parser
from .generate_script_config import RuntimeContext, load_runtime_context, resolve_paths
from .generate_script_runner import (
    generate_authoring_with_retries,
    generate_chunked_authoring,
    log_runtime_context,
    run_plain_script_validation,
    write_outputs,
)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context = load_runtime_context(
        repo_root=resolve_project_root(Path.cwd()),
        mode_arg=args.mode,
        brief_arg=args.brief,
        output_arg=args.output,
        system_prompt_arg=args.system_prompt,
    )

    if not context.paths.system_prompt_path.exists():
        eprint(f"[WARN] System prompt not found at: {context.paths.system_prompt_path} (using minimal system prompt).")

    log_runtime_context(context)
    client = LLMClient(context.llm_config)

    if args.chunked:
        try:
            authoring = generate_chunked_authoring(client=client, context=context, chunk_size=args.chunk_size)
        except Exception as exc:
            raise SystemExit(f"[ERROR] Chunked generation failed. Last error: {exc}") from exc
    else:
        authoring = generate_authoring_with_retries(client=client, context=context, retries=args.retries)

    write_outputs(authoring, context)
    if args.validate:
        run_plain_script_validation(context)
    return 0


__all__ = [
    "ALLOWED_SCRIPT_ZONES",
    "LLMClient",
    "LLMConfig",
    "RuntimeContext",
    "build_default_zone_counts",
    "build_meta_outline_prompt",
    "build_parser",
    "build_user_prompt",
    "build_zone_chunk_prompt",
    "dedupe_authoring_script_inplace",
    "dedupe_script_items",
    "default_brief_filename_for_mode",
    "default_prompt_filename_for_mode",
    "env_float",
    "env_int",
    "eprint",
    "extract_json",
    "extract_json_array",
    "force_single_sentence_items_inplace",
    "generate_authoring_with_retries",
    "generate_chunked_authoring",
    "load_runtime_context",
    "load_yaml",
    "log_runtime_context",
    "main",
    "normalize_chunk_items_to_single_sentence",
    "normalize_output_base",
    "normalize_story_mode",
    "prune_outline_echoes_inplace",
    "prune_story_drift_inplace",
    "prune_zone_misplaced_boilerplate_inplace",
    "read_text",
    "repair_authoring_single_sentence_inplace",
    "resolve_paths",
    "run_plain_script_validation",
    "sanitize_authoring_inplace",
    "semantic_motif_cap_inplace",
    "spec_render_plain_script",
    "validate_authoring",
    "write_json",
    "write_outputs",
    "write_text",
]


if __name__ == "__main__":
    raise SystemExit(main())
