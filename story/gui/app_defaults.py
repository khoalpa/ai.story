from __future__ import annotations

from pathlib import Path

from story.service import default_prompt_filename_for_mode
from story.paths import resolve_project_root

FALLBACK_SYSTEM_PROMPT = """You are a connectivity test assistant. Reply briefly and clearly. When asked for JSON, return valid JSON only."""


def default_system_prompt(mode: str, project_root: Path | None = None) -> str:
    try:
        root = resolve_project_root(project_root)
        candidate = Path(default_prompt_filename_for_mode(mode))
        path = candidate if candidate.is_absolute() else (root / candidate).resolve()
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, ValueError):
        return FALLBACK_SYSTEM_PROMPT
