"""Runtime projection of the latest canonical authoring prompt.

The prompt remains the normative source.  This module extracts the small,
deterministic subset that repository tooling can actually verify.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

PROMPT_FILENAME = re.compile(r"^ChatGPT_prompt_v(\d+)\.(\d+)\.(\d+)\.txt$", re.IGNORECASE)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPTS_DIRECTORY = PROJECT_ROOT / "prompts"
PROMPTS_DIRECTORY_ENV = "AI_STUDIO_PROMPTS_DIR"


@dataclass(frozen=True)
class PromptContract:
    path: Path
    version: tuple[int, int, int]
    sha256: str
    image_basenames: tuple[str, ...]
    landscape_size: tuple[int, int]
    portrait_size: tuple[int, int]
    story_validation_schema_version: str
    package_quality_schema_version: str
    series_anchor_schema_version: str
    story_quality_commitment_schema_version: str
    environment_whitelist: tuple[str, ...]

    @property
    def version_label(self) -> str:
        return ".".join(str(part) for part in self.version)


def _version(path: Path) -> tuple[int, int, int]:
    match = PROMPT_FILENAME.match(path.name)
    if match is None:
        raise ValueError(f"Tên prompt không hợp lệ: {path.name}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def discover_canonical_prompts(directory: Path = DEFAULT_PROMPTS_DIRECTORY) -> list[Path]:
    if not directory.is_dir():
        return []
    paths = [path for path in directory.iterdir() if path.is_file() and PROMPT_FILENAME.match(path.name)]
    return sorted(paths, key=_version, reverse=True)


def prompt_directories() -> tuple[Path, ...]:
    candidates: list[Path] = []
    configured = os.environ.get(PROMPTS_DIRECTORY_ENV, "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend((Path.cwd() / "prompts", DEFAULT_PROMPTS_DIRECTORY))
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def canonical_prompt_path(directory: Path | None = None) -> Path:
    directories = (directory,) if directory is not None else prompt_directories()
    for candidate in directories:
        paths = discover_canonical_prompts(candidate)
        if paths:
            return paths[0]
    searched = ", ".join(str(item) for item in directories)
    raise FileNotFoundError(
        f"Không tìm thấy ChatGPT_prompt_v*.*.*.txt trong: {searched}. "
        f"Có thể đặt {PROMPTS_DIRECTORY_ENV}."
    )


def _literal(text: str, name: str) -> str:
    match = re.search(rf"^- {re.escape(name)}\s*=\s*([^\r\n]+)$", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Prompt thiếu literal canonical: {name}")
    return match.group(1).strip().strip('"')


def _size(text: str, name: str) -> tuple[int, int]:
    value = _literal(text, name)
    match = re.fullmatch(r"(\d+)\s*x\s*(\d+)", value, re.IGNORECASE)
    if match is None:
        raise ValueError(f"{name} không có dạng WIDTH x HEIGHT: {value}")
    return int(match.group(1)), int(match.group(2))


def load_prompt_contract(path: Path | None = None) -> PromptContract:
    resolved = (path or canonical_prompt_path()).resolve()
    raw = resolved.read_bytes()
    text = raw.decode("utf-8-sig")
    basenames_match = re.search(r"`IMAGE_BASENAME_SET\s*=\s*\[([^]]+)\]`", text)
    environment_match = re.search(
        r"SHARED ENVIRONMENT WHITELIST:\s*\n- (?P<values>[^\n]+)", text
    )
    if basenames_match is None or environment_match is None:
        raise ValueError("Prompt thiếu IMAGE_BASENAME_SET hoặc SHARED ENVIRONMENT WHITELIST")
    basenames = tuple(value.strip() for value in basenames_match.group(1).split(","))
    environments = tuple(re.findall(r'"([^"]+)"', environment_match.group("values")))
    return PromptContract(
        path=resolved,
        version=_version(resolved),
        sha256=hashlib.sha256(raw).hexdigest(),
        image_basenames=basenames,
        landscape_size=_size(text, "LANDSCAPE_SIZE"),
        portrait_size=_size(text, "PORTRAIT_SIZE"),
        story_validation_schema_version=_literal(text, "STORY_VALIDATION_REPORT_SCHEMA_VERSION"),
        package_quality_schema_version=_literal(text, "PACKAGE_QUALITY_REPORT_SCHEMA_VERSION"),
        series_anchor_schema_version=_literal(text, "SERIES_ANCHOR_SCHEMA_VERSION"),
        story_quality_commitment_schema_version=_literal(text, "STORY_QUALITY_COMMITMENT_SCHEMA_VERSION"),
        environment_whitelist=environments,
    )


__all__ = [
    "DEFAULT_PROMPTS_DIRECTORY", "PROJECT_ROOT", "PromptContract", "canonical_prompt_path",
    "discover_canonical_prompts", "load_prompt_contract", "prompt_directories",
]
