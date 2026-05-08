from __future__ import annotations

from pathlib import Path
import re
import unicodedata

from story.paths import resolve_modes_root, resolve_project_root

DEFAULT_BASE_STORY_MODES = ("trend", "calm")
MODE_BRIEF_MARKERS = ("_brief",)
MODE_PROMPT_MARKERS = ("_prompt",)
MODE_FILE_PATTERNS = ("*.yml", "*.yaml", "*.txt", "*.prompt")
MODE_FIELD_PATTERNS = {
    "brief": ("*.yml", "*.yaml"),
    "prompt": ("*.txt", "*.prompt"),
}


def _slugify_mode_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    return lowered.strip("_")


def _mode_key_from_asset_stem(stem: str) -> str:
    for marker in MODE_PROMPT_MARKERS:
        if marker in stem:
            prefix, suffix = stem.split(marker, 1)
            return _slugify_mode_key(f"{prefix}{suffix}")
    for marker in MODE_BRIEF_MARKERS:
        if marker in stem:
            prefix, suffix = stem.split(marker, 1)
            return _slugify_mode_key(f"{prefix}{suffix}")
    return _slugify_mode_key(stem)


def _discover_mode_ids_from_modes_root(modes_root: Path) -> list[str]:
    if not modes_root.exists() or not modes_root.is_dir():
        return []
    mode_ids: list[str] = []
    seen: set[str] = set()
    for pattern in MODE_FILE_PATTERNS:
        for path in sorted(modes_root.glob(pattern)):
            mode_id = _mode_key_from_asset_stem(path.stem)
            if not mode_id or mode_id in seen:
                continue
            seen.add(mode_id)
            mode_ids.append(mode_id)
    return mode_ids


def list_story_mode_ids(project_root: Path | None = None, modes_root: Path | None = None) -> list[str]:
    root = resolve_project_root(project_root)
    resolved_modes_root = (modes_root or resolve_modes_root(root)).expanduser().resolve()
    discovered = _discover_mode_ids_from_modes_root(resolved_modes_root)
    if discovered:
        return discovered
    return list(DEFAULT_BASE_STORY_MODES)


def story_mode_label(mode: str, project_root: Path | None = None) -> str:
    normalized_mode = _slugify_mode_key(mode)
    if not normalized_mode:
        return "trend"
    return normalized_mode.replace("_", " ").title()


def story_mode_base_mode(mode: str, project_root: Path | None = None) -> str:
    normalized_mode = _slugify_mode_key(mode)
    if normalized_mode in DEFAULT_BASE_STORY_MODES:
        return normalized_mode
    return "trend"


def _mode_asset_path_for_field(
    mode: str,
    field: str,
    project_root: Path | None = None,
    modes_root: Path | None = None,
) -> Path | None:
    patterns = MODE_FIELD_PATTERNS.get(field)
    if not patterns:
        return None
    root = resolve_project_root(project_root)
    resolved_modes_root = (modes_root or resolve_modes_root(root)).expanduser().resolve()
    if not resolved_modes_root.exists() or not resolved_modes_root.is_dir():
        return None
    normalized_mode = _slugify_mode_key(mode)
    fallback_matches: list[tuple[int, Path]] = []
    for pattern in patterns:
        for path in sorted(resolved_modes_root.glob(pattern)):
            asset_mode = _mode_key_from_asset_stem(path.stem)
            if asset_mode == normalized_mode:
                return path.resolve()
            if normalized_mode.startswith(f"{asset_mode}_") or asset_mode.startswith(f"{normalized_mode}_"):
                fallback_matches.append((len(asset_mode), path.resolve()))
    if fallback_matches:
        fallback_matches.sort(key=lambda item: (-item[0], str(item[1])))
        return fallback_matches[0][1]
    return None


def resolve_preset_path(
    mode: str,
    field: str,
    project_root: Path | None = None,
    modes_root: Path | None = None,
) -> Path | None:
    return _mode_asset_path_for_field(mode, field, project_root=project_root, modes_root=modes_root)


def preset_source_summary(
    mode: str,
    project_root: Path | None = None,
    modes_root: Path | None = None,
) -> dict[str, str]:
    return {
        "modes_root": str((modes_root or resolve_modes_root(resolve_project_root(project_root))).expanduser()),
        "mode": _slugify_mode_key(mode),
        "label": story_mode_label(mode, project_root=project_root),
        "base_mode": story_mode_base_mode(mode, project_root=project_root),
        "brief": str(resolve_preset_path(mode, "brief", project_root=project_root, modes_root=modes_root) or ""),
        "prompt": str(resolve_preset_path(mode, "prompt", project_root=project_root, modes_root=modes_root) or ""),
    }
