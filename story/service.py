from __future__ import annotations

"""Backward-compatible facade for split generation modules."""

from .client import LLMClient, LLMConfig
from .common import (
    ALLOWED_DSL_TAGS,
    JSON_FENCE_ARR_RE,
    JSON_FENCE_OBJ_RE,
    SQUARE_BRACKET_RE,
    SUPPORTED_STORY_MODES,
    default_brief_filename_for_mode,
    default_prompt_filename_for_mode,
    env_float,
    env_int,
    eprint,
    load_yaml,
    normalize_output_base,
    normalize_story_mode,
    read_text,
    write_json,
    write_text,
)
from .dedupe import dedupe_authoring_script_inplace, dedupe_script_items, sanitize_spoken_text
from .normalization import (
    coerce_text_to_single_sentence,
    ensure_script_zone_order_inplace,
    normalize_chunk_items_to_single_sentence,
    sanitize_authoring_inplace,
)
from .orchestration import (
    post_process_authoring,
    prune_outline_echoes_inplace,
    prune_story_drift_inplace,
    prune_zone_misplaced_boilerplate_inplace,
    semantic_motif_cap_inplace,
)
from .parsing import (
    extract_json,
    extract_json_array,
    find_illegal_square_brackets,
    validate_authoring,
)
from .prompting import (
    build_default_zone_counts,
    build_meta_outline_prompt,
    build_user_prompt,
    build_zone_chunk_prompt,
)
from .repair import force_single_sentence_items_inplace, repair_authoring_single_sentence_inplace

__all__ = [
    "ALLOWED_DSL_TAGS",
    "JSON_FENCE_ARR_RE",
    "JSON_FENCE_OBJ_RE",
    "LLMClient",
    "LLMConfig",
    "SQUARE_BRACKET_RE",
    "SUPPORTED_STORY_MODES",
    "build_default_zone_counts",
    "build_meta_outline_prompt",
    "build_user_prompt",
    "build_zone_chunk_prompt",
    "coerce_text_to_single_sentence",
    "ensure_script_zone_order_inplace",
    "dedupe_authoring_script_inplace",
    "dedupe_script_items",
    "default_brief_filename_for_mode",
    "default_prompt_filename_for_mode",
    "env_float",
    "env_int",
    "eprint",
    "extract_json",
    "extract_json_array",
    "find_illegal_square_brackets",
    "force_single_sentence_items_inplace",
    "load_yaml",
    "normalize_chunk_items_to_single_sentence",
    "normalize_output_base",
    "normalize_story_mode",
    "post_process_authoring",
    "prune_outline_echoes_inplace",
    "prune_story_drift_inplace",
    "prune_zone_misplaced_boilerplate_inplace",
    "read_text",
    "repair_authoring_single_sentence_inplace",
    "sanitize_authoring_inplace",
    "sanitize_spoken_text",
    "semantic_motif_cap_inplace",
    "validate_authoring",
    "write_json",
    "write_text",
]
