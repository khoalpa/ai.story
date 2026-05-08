from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .service import (
    LLMConfig,
    default_brief_filename_for_mode,
    default_prompt_filename_for_mode,
    env_float,
    env_int,
    load_yaml,
    normalize_output_base,
    normalize_story_mode,
    read_text,
)


@dataclass(frozen=True)
class ResolvedPaths:
    repo_root: Path
    brief_path: Path
    system_prompt_path: Path
    output_base: Path


@dataclass(frozen=True)
class RuntimeContext:
    mode: str
    brief: dict[str, Any]
    system_prompt: str
    paths: ResolvedPaths
    llm_config: LLMConfig
    min_lines: int


def resolve_paths(*, repo_root: Path, mode_arg: str, brief_arg: str | None, output_arg: str, system_prompt_arg: str | None) -> tuple[str, ResolvedPaths]:
    mode = normalize_story_mode(mode_arg)
    brief_candidate = Path(brief_arg or default_brief_filename_for_mode(mode))
    env_prompt = os.getenv("AUDIO_STORY_SYSTEM_PROMPT")
    system_prompt_candidate = (
        Path(system_prompt_arg)
        if system_prompt_arg
        else (Path(env_prompt) if env_prompt else (repo_root / default_prompt_filename_for_mode(mode)))
    )

    brief_path = brief_candidate if brief_candidate.is_absolute() else (repo_root / brief_candidate).resolve()
    system_prompt_path = system_prompt_candidate if system_prompt_candidate.is_absolute() else (repo_root / system_prompt_candidate).resolve()
    output_base = normalize_output_base(output_arg)

    return mode, ResolvedPaths(
        repo_root=repo_root,
        brief_path=brief_path,
        system_prompt_path=system_prompt_path,
        output_base=output_base,
    )


def load_runtime_context(*, repo_root: Path, mode_arg: str, brief_arg: str | None, output_arg: str, system_prompt_arg: str | None) -> RuntimeContext:
    mode, paths = resolve_paths(
        repo_root=repo_root,
        mode_arg=mode_arg,
        brief_arg=brief_arg,
        output_arg=output_arg,
        system_prompt_arg=system_prompt_arg,
    )

    if not paths.brief_path.exists():
        raise SystemExit(f"[ERROR] Brief not found: {paths.brief_path}")

    if paths.system_prompt_path.exists():
        system_prompt = read_text(paths.system_prompt_path)
    else:
        system_prompt = "You are a helpful assistant. Output must be valid JSON only."

    brief = load_yaml(paths.brief_path)
    duration_min = int((brief.get("goals") or {}).get("target_duration_min", 0) or 0)
    min_lines_env = env_int("AUDIO_STORY_MIN_LINES", 0)
    min_lines = duration_min * 12 if duration_min > 0 else 120
    if min_lines_env > 0:
        min_lines = min_lines_env

    llm_config = LLMConfig(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
        model=os.getenv("LLM_MODEL", "local-model"),
        timeout_s=env_int("LLM_TIMEOUT", 120),
        max_tokens=env_int("LLM_MAX_TOKENS", 65536),
        temperature=env_float("LLM_TEMPERATURE", 0.7),
        api_key=os.getenv("LLM_API_KEY", "not-needed"),
        local_update_target=os.getenv("LLM_LOCAL_UPDATE_TARGET", ""),
    )

    return RuntimeContext(
        mode=mode,
        brief=brief,
        system_prompt=system_prompt,
        paths=paths,
        llm_config=llm_config,
        min_lines=min_lines,
    )
