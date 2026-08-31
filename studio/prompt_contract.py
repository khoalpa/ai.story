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
from types import MappingProxyType
from typing import Any, Mapping

PROMPT_FILENAME = re.compile(r"^(?:[0-9]+-)?ChatGPT_prompt_v(\d+)\.(\d+)\.(\d+)\.txt$", re.IGNORECASE)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPTS_DIRECTORY = PROJECT_ROOT / "prompts"
PROMPTS_DIRECTORY_ENV = "AI_STUDIO_PROMPTS_DIR"
PROMPT_FILE_ENV = "AI_STUDIO_PROMPT_FILE"


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
    workflow_manifest_schema_version: str | None = None
    workflow_package_stages: tuple[str, ...] = ()
    workflow_package_purposes: tuple[str, ...] = ()
    workflow_operation_modes: tuple[str, ...] = ()
    workflow_mutation_statuses: tuple[str, ...] = ()
    video_prompt_schema_version: str | None = None
    story_schema_version: str | None = None
    video_prompt_file_name: str = "video_prompts.json"
    video_prompt_derivative_targets: tuple[str, ...] = ()
    video_aspect_ratios: tuple[str, ...] = ()
    video_coverage_modes: tuple[str, ...] = ()
    video_clip_durations: tuple[int, ...] = ()
    video_audio_modes: tuple[str, ...] = ()
    video_continuity_modes: tuple[str, ...] = ()
    video_generation_modes: tuple[str, ...] = ()
    video_prompt_languages: tuple[str, ...] = ()
    video_capability_statuses: tuple[str, ...] = ()
    video_transition_types: tuple[str, ...] = ()
    video_prompt_default_config: Mapping[str, Any] | None = None
    video_prompt_target_word_min: int = 90
    video_prompt_target_word_max: int = 180
    video_prompt_hard_max_words: int = 240
    video_audio_prompt_hard_max_words: int = 60
    video_avoid_item_max_count: int = 12
    video_max_character_references_per_clip: int = 3
    artifact_path_format_registry: Mapping[str, Any] | None = None
    current_public_schema_registry: Mapping[str, Any] | None = None
    current_enum_registry: Mapping[str, Any] | None = None
    current_config_registry: Mapping[str, Any] | None = None

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
    if directory is None:
        configured_file = os.environ.get(PROMPT_FILE_ENV, "").strip()
        if configured_file:
            path = Path(configured_file).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Không tìm thấy tệp prompt đã chọn: {path}")
            _version(path)
            return path
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


class _LiteralParser:
    """Parse the prompt's bounded JSON-like registry notation without eval."""

    def __init__(self, value: str) -> None:
        self.tokens = re.findall(r'"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+', value)
        self.index = 0

    def parse(self) -> Any:
        value = self._value()
        if self.index != len(self.tokens):
            raise ValueError(f"Literal còn token thừa: {self.tokens[self.index]!r}")
        return value

    def _take(self) -> str:
        if self.index >= len(self.tokens):
            raise ValueError("Literal kết thúc ngoài dự kiến")
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _value(self) -> Any:
        token = self._take()
        if token == "[":
            result: list[Any] = []
            if self.index < len(self.tokens) and self.tokens[self.index] == "]":
                self.index += 1
                return result
            while True:
                result.append(self._value())
                separator = self._take()
                if separator == "]":
                    return result
                if separator != ",":
                    raise ValueError("Array literal thiếu dấu phẩy")
        if token == "{":
            result: dict[str, Any] = {}
            if self.index < len(self.tokens) and self.tokens[self.index] == "}":
                self.index += 1
                return result
            while True:
                key = self._atom(self._take())
                if not isinstance(key, str) or self._take() != ":":
                    raise ValueError("Map literal có key/dấu hai chấm không hợp lệ")
                if key in result:
                    raise ValueError(f"Map literal có key trùng: {key}")
                result[key] = self._value()
                separator = self._take()
                if separator == "}":
                    return result
                if separator != ",":
                    raise ValueError("Map literal thiếu dấu phẩy")
        return self._atom(token)

    @staticmethod
    def _atom(token: str) -> Any:
        if token.startswith('"'):
            import json
            return json.loads(token)
        if token == "true":
            return True
        if token == "false":
            return False
        if token == "null":
            return None
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", token):
            return float(token)
        return token


def _parsed_literal(text: str, name: str) -> Any:
    match = re.search(rf"^- {re.escape(name)}\s*=\s*([^\r\n]+)$", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Prompt thiếu literal canonical: {name}")
    return _LiteralParser(match.group(1).strip()).parse()


def _optional_parsed(text: str, name: str, default: Any) -> Any:
    return _parsed_literal(text, name) if f"- {name} =" in text else default


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _resolved_registry(text: str, name: str) -> Mapping[str, Any]:
    registry = _parsed_literal(text, name)
    if not isinstance(registry, dict):
        raise ValueError(f"{name} phải là map")

    def resolve(value: Any, stack: tuple[str, ...]) -> Any:
        if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", value) and f"- {value} =" in text:
            if value in stack:
                raise ValueError(f"Circular prompt literal reference: {' -> '.join((*stack, value))}")
            return resolve(_parsed_literal(text, value), (*stack, value))
        if isinstance(value, dict):
            return {key: resolve(child, stack) for key, child in value.items()}
        if isinstance(value, list):
            return [resolve(child, stack) for child in value]
        return value

    return _freeze(resolve(registry, (name,)))


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
        workflow_manifest_schema_version=(
            _literal(text, "WORKFLOW_MANIFEST_SCHEMA_VERSION")
            if "- WORKFLOW_MANIFEST_SCHEMA_VERSION =" in text else None
        ),
        workflow_package_stages=(
            tuple(_parsed_literal(text, "WORKFLOW_PACKAGE_STAGE_ENUM"))
            if "- WORKFLOW_PACKAGE_STAGE_ENUM =" in text else ()
        ),
        workflow_package_purposes=tuple(_optional_parsed(text, "WORKFLOW_PACKAGE_PURPOSE_ENUM", [])),
        workflow_operation_modes=tuple(_optional_parsed(text, "WORKFLOW_OPERATION_MODE_ENUM", [])),
        workflow_mutation_statuses=tuple(_optional_parsed(text, "WORKFLOW_MUTATION_STATUS_ENUM", [])),
        video_prompt_schema_version=(
            _literal(text, "VIDEO_PROMPT_SCHEMA_VERSION")
            if "- VIDEO_PROMPT_SCHEMA_VERSION =" in text
            else None
        ),
        story_schema_version=_optional_parsed(text, "STORY_SCHEMA_VERSION", None),
        video_prompt_file_name=_optional_parsed(text, "VIDEO_PROMPT_FILE_NAME", "video_prompts.json"),
        video_prompt_derivative_targets=tuple(_optional_parsed(text, "VIDEO_PROMPT_DERIVATIVE_TARGET_ENUM", [])),
        video_aspect_ratios=tuple(_optional_parsed(text, "VIDEO_ASPECT_RATIO_ENUM", [])),
        video_coverage_modes=tuple(_optional_parsed(text, "VIDEO_COVERAGE_MODE_ENUM", [])),
        video_clip_durations=tuple(_optional_parsed(text, "VIDEO_CLIP_DURATION_SECONDS_ENUM", [])),
        video_audio_modes=tuple(_optional_parsed(text, "VIDEO_AUDIO_MODE_ENUM", [])),
        video_continuity_modes=tuple(_optional_parsed(text, "VIDEO_CONTINUITY_MODE_ENUM", [])),
        video_generation_modes=tuple(_optional_parsed(text, "VIDEO_GENERATION_MODE_ENUM", [])),
        video_prompt_languages=tuple(_optional_parsed(text, "VIDEO_PROMPT_LANGUAGE_ENUM", [])),
        video_capability_statuses=tuple(_optional_parsed(text, "VIDEO_CAPABILITY_STATUS_ENUM", [])),
        video_transition_types=tuple(_optional_parsed(text, "VIDEO_TRANSITION_TYPE_ENUM", [])),
        video_prompt_default_config=_freeze(_optional_parsed(text, "VIDEO_PROMPT_DEFAULT_CONFIG", {})),
        video_prompt_target_word_min=_optional_parsed(text, "VIDEO_PROMPT_TARGET_WORD_MIN", 90),
        video_prompt_target_word_max=_optional_parsed(text, "VIDEO_PROMPT_TARGET_WORD_MAX", 180),
        video_prompt_hard_max_words=_optional_parsed(text, "VIDEO_PROMPT_HARD_MAX_WORDS", 240),
        video_audio_prompt_hard_max_words=_optional_parsed(text, "VIDEO_AUDIO_PROMPT_HARD_MAX_WORDS", 60),
        video_avoid_item_max_count=_optional_parsed(text, "VIDEO_AVOID_ITEM_MAX_COUNT", 12),
        video_max_character_references_per_clip=_optional_parsed(text, "VIDEO_PROMPT_MAX_CHARACTER_REFERENCES_PER_CLIP", 3),
        artifact_path_format_registry=_freeze(_optional_parsed(text, "ARTIFACT_PATH_FORMAT_REGISTRY", {})),
        current_public_schema_registry=_resolved_registry(text, "CURRENT_PUBLIC_SCHEMA_REGISTRY"),
        current_enum_registry=_resolved_registry(text, "CURRENT_ENUM_REGISTRY"),
        current_config_registry=_resolved_registry(text, "CURRENT_CONFIG_REGISTRY"),
    )


__all__ = [
    "DEFAULT_PROMPTS_DIRECTORY", "PROJECT_ROOT", "PROMPT_FILE_ENV", "PromptContract", "canonical_prompt_path",
    "discover_canonical_prompts", "load_prompt_contract", "prompt_directories",
]
