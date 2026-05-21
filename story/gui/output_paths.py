from __future__ import annotations

from pathlib import Path
from typing import Any

import json

from story.paths import PROJECT_ROOT


DEFAULT_STORY_OUTPUT_BASE = Path("output/story/story")


def resolve_story_output_base(output_base: str | Path | None = None) -> Path:
    base = Path(str(output_base or DEFAULT_STORY_OUTPUT_BASE)).expanduser()
    if not base.is_absolute():
        base = PROJECT_ROOT / base
    return base.resolve()


def story_step_output_path(output_base: str | Path | None, step: str) -> Path:
    base = resolve_story_output_base(output_base)
    return base.with_name(f"{base.stem}_{step}").with_suffix(".json")


def save_story_step_json(payload: Any, *, output_base: str | Path | None, step: str) -> Path:
    path = story_step_output_path(output_base, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return path
