from __future__ import annotations

from pathlib import Path

from story.gui.presets import resolve_preset_path
from story.paths import resolve_assets_root, resolve_modes_root, resolve_project_root


def _display_path_label(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


PROMPT_GLOB_PATTERNS = ("*.txt", "*.prompt")


def list_system_prompt_files(project_root: Path | None = None, modes_root: Path | None = None) -> list[Path]:
    root = resolve_project_root(project_root)
    assets_root = resolve_assets_root(root)
    resolved_modes_root = (modes_root or resolve_modes_root(root)).expanduser()
    candidates: list[Path] = []
    search_dirs = [resolved_modes_root, assets_root]
    for directory in search_dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        for pattern in PROMPT_GLOB_PATTERNS:
            candidates.extend(sorted(directory.glob(pattern)))
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in sorted(candidates):
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def make_system_prompt_option_labels(paths: list[Path], project_root: Path | None = None) -> list[str]:
    root = resolve_project_root(project_root)
    labels = ["(current editor)"]
    for path in paths:
        labels.append(_display_path_label(path, root))
    return labels


def selected_system_prompt_path(selection: str, paths: list[Path], project_root: Path | None = None) -> Path | None:
    if selection == "(current editor)":
        return None
    labels = make_system_prompt_option_labels(paths, project_root=project_root)
    mapping = {label: path for label, path in zip(labels[1:], paths, strict=False)}
    return mapping.get(selection)


def recommended_system_prompt_path_for_mode(
    mode: str,
    paths: list[Path],
    project_root: Path | None = None,
    modes_root: Path | None = None,
) -> Path | None:
    preset_hit = resolve_preset_path(mode, "prompt", project_root=project_root, modes_root=modes_root)
    if preset_hit is not None and preset_hit in paths:
        return preset_hit
    mode_key = mode.strip().lower()
    if not mode_key:
        return None
    exact_hits = [path for path in paths if mode_key in path.stem.lower()]
    if exact_hits:
        return exact_hits[0]
    parent_hits = [path for path in paths if mode_key in str(path.parent).lower()]
    if parent_hits:
        return parent_hits[0]
    return paths[0] if paths else None


def recommended_system_prompt_label_for_mode(
    mode: str,
    paths: list[Path],
    project_root: Path | None = None,
    modes_root: Path | None = None,
) -> str:
    chosen = recommended_system_prompt_path_for_mode(mode, paths, project_root=project_root, modes_root=modes_root)
    if chosen is None:
        return "(current editor)"
    labels = make_system_prompt_option_labels(paths, project_root=project_root)
    mapping = {path: label for label, path in zip(labels[1:], paths, strict=False)}
    return mapping.get(chosen, "(current editor)")


def load_system_prompt_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
