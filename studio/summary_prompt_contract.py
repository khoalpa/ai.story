"""Discovery and validation for summary authoring prompts."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from studio.prompt_contract import DEFAULT_PROMPTS_DIRECTORY, prompt_directories

CURRENT_SUMMARY_PROMPT_VERSION = (1, 5, 0)
CURRENT_SUMMARY_PROMPT_FILENAME = "summary_prompt_v1.5.0.txt"
CURRENT_SUMMARY_QUICKSTART_FILENAME = "summary_prompt_v1.5.0_quickstart.txt"
SUPPORTED_SUMMARY_PROMPT_VERSIONS = (CURRENT_SUMMARY_PROMPT_VERSION,)
SUPPORTED_SUMMARY_PROMPT_FILENAMES = tuple(
    f"summary_prompt_v{'.'.join(map(str, version))}.txt"
    for version in SUPPORTED_SUMMARY_PROMPT_VERSIONS
)
SUMMARY_PROMPT_FILENAME = re.compile(
    r"^summary_prompt_v(\d+)\.(\d+)\.(\d+)\.txt$", re.IGNORECASE
)


@dataclass(frozen=True)
class SummaryPromptContract:
    path: Path
    version: tuple[int, int, int]
    sha256: str
    summary_schema_version: str = "1.1.0"
    story_projection_schema_version: str = "4.1.3"
    plain_script_format_version: str = "1.1.0"
    default_image_mode: str = "SCENE"

    @property
    def version_label(self) -> str:
        return ".".join(map(str, self.version))


def summary_prompt_version(path: Path) -> tuple[int, int, int]:
    match = SUMMARY_PROMPT_FILENAME.match(path.name)
    if match is None:
        raise ValueError(f"Tên summary prompt không hợp lệ: {path.name}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def discover_summary_prompts(
    directory: Path = DEFAULT_PROMPTS_DIRECTORY,
) -> list[Path]:
    if not directory.is_dir():
        return []
    return [
        directory / name
        for name in SUPPORTED_SUMMARY_PROMPT_FILENAMES
        if (directory / name).is_file()
    ]


def discover_available_summary_prompts() -> list[Path]:
    """Discover supported summary prompts across source and installed locations."""
    paths: list[Path] = []
    seen_names: set[str] = set()
    for directory in prompt_directories():
        for path in discover_summary_prompts(directory):
            if path.name not in seen_names:
                paths.append(path)
                seen_names.add(path.name)
    return paths


def load_summary_prompt_contract(path: Path) -> SummaryPromptContract:
    if path.name not in SUPPORTED_SUMMARY_PROMPT_FILENAMES:
        raise ValueError(
            "Chỉ hỗ trợ " + ", ".join(SUPPORTED_SUMMARY_PROMPT_FILENAMES) + "."
        )
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Summary prompt không phải UTF-8 hợp lệ: {exc}") from exc
    version = summary_prompt_version(path)
    version_label = ".".join(map(str, version))
    if not text.startswith(f"CHATGPT SUMMARY & ANALYSIS PACKAGE — v{version_label}"):
        raise ValueError(f"Nội dung không phải summary prompt v{version_label}.")
    required = (
        "summary.json canonical",
        'schema_version="1.1.0"',
        "summary_narration.txt",
        "AUDIO_STORY_PLAIN v1.1.0",
        'schema_version="4.1.3"',
        "summary_visual_plan.json",
        "image_mode=SCENE",
        "summary_manifest.json",
        "summary_render_plan.json",
        "summary_media_review.json",
        "summary_stage1.zip",
        "summary_stage2.zip",
        "summary_stage.json",
        "ai-summary-stage3",
        "ai-summary-render",
        "summary_media_review_draft.json",
        "`landscape/` và `portrait/`",
        "studio.summary_schema.validate_summary_document",
        "FULL_SUMMARY` ánh xạ thành video coverage `FULL_STORY",
        "ai-story-audit <path> --type summary",
        "studio.summary_exports.export_citations",
    )
    missing = [literal for literal in required if literal not in text]
    if missing:
        raise ValueError("Summary prompt thiếu contract bắt buộc: " + ", ".join(missing))
    return SummaryPromptContract(path, version, hashlib.sha256(raw).hexdigest())


def current_summary_prompt_path(
    directory: Path | None = None,
) -> Path:
    if directory is not None:
        path = directory / CURRENT_SUMMARY_PROMPT_FILENAME
        if path.is_file():
            return path
        raise FileNotFoundError(f"Không tìm thấy {path}")
    for candidate in prompt_directories():
        path = candidate / CURRENT_SUMMARY_PROMPT_FILENAME
        if path.is_file():
            return path
    raise FileNotFoundError(f"Không tìm thấy {CURRENT_SUMMARY_PROMPT_FILENAME}")


def current_summary_quickstart_path(directory: Path | None = None) -> Path:
    directories = (directory,) if directory is not None else tuple(prompt_directories())
    for candidate in directories:
        path = candidate / CURRENT_SUMMARY_QUICKSTART_FILENAME
        if path.is_file():
            return path
    raise FileNotFoundError(f"Không tìm thấy {CURRENT_SUMMARY_QUICKSTART_FILENAME}")


__all__ = [
    "CURRENT_SUMMARY_PROMPT_FILENAME",
    "CURRENT_SUMMARY_PROMPT_VERSION",
    "CURRENT_SUMMARY_QUICKSTART_FILENAME",
    "SUMMARY_PROMPT_FILENAME",
    "SUPPORTED_SUMMARY_PROMPT_FILENAMES",
    "SummaryPromptContract",
    "current_summary_prompt_path",
    "current_summary_quickstart_path",
    "discover_available_summary_prompts",
    "discover_summary_prompts",
    "load_summary_prompt_contract",
    "summary_prompt_version",
]
