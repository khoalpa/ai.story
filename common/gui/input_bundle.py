from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROMPT_FILE_NAMES: tuple[str, ...] = (
    "cover_prompt.json",
    "scene_prompt.json",
    "intro_prompt.json",
    "greeting_prompt.json",
    "opening_prompt.json",
    "introduction_prompt.json",
    "development_prompt.json",
    "climax_prompt.json",
    "falling_prompt.json",
    "ending_prompt.json",
    "farewell_prompt.json",
    "outro_prompt.json",
)


@dataclass(frozen=True)
class InputBundle:
    root: Path
    story_path: Path
    prompt_files: tuple[Path, ...]
    story_error: str = ""
    prompt_error: str = ""

    @property
    def has_story(self) -> bool:
        return self.story_path.is_file() and not self.story_error

    @property
    def has_prompts(self) -> bool:
        return bool(self.prompt_files) and not self.prompt_error

    @property
    def is_ready(self) -> bool:
        return self.has_story or self.has_prompts

    def summary(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "story": str(self.story_path) if self.story_path.is_file() else "",
            "story_ready": self.has_story,
            "story_error": self.story_error,
            "prompt_count": len(self.prompt_files),
            "prompt_files": [path.name for path in self.prompt_files],
            "prompts_ready": self.has_prompts,
            "prompt_error": self.prompt_error,
        }


def default_input_root() -> Path:
    return Path("input")


def resolve_workspace_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def scan_input_bundle(input_root: str | Path = default_input_root()) -> InputBundle:
    root = resolve_workspace_path(input_root)
    story_path = root / "story.json"
    prompt_files = tuple(path for path in (root / name for name in PROMPT_FILE_NAMES) if path.is_file())

    story_error = ""
    if story_path.is_file():
        try:
            json.loads(story_path.read_text(encoding="utf-8"))
        except Exception as exc:
            story_error = str(exc)

    prompt_error = ""
    for prompt_file in prompt_files:
        try:
            data = json.loads(prompt_file.read_text(encoding="utf-8"))
        except Exception as exc:
            prompt_error = f"{prompt_file.name}: {exc}"
            break
        if not isinstance(data, dict) or not str(data.get("prompt") or "").strip():
            prompt_error = f"{prompt_file.name}: missing prompt"
            break

    return InputBundle(root=root, story_path=story_path, prompt_files=prompt_files, story_error=story_error, prompt_error=prompt_error)


def load_input_story(input_root: str | Path = default_input_root()) -> dict[str, Any]:
    bundle = scan_input_bundle(input_root)
    if not bundle.story_path.is_file():
        raise FileNotFoundError(f"Input story not found: {bundle.story_path}")
    if bundle.story_error:
        raise ValueError(bundle.story_error)
    data = json.loads(bundle.story_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Input story JSON must be an object.")
    return data
