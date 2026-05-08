from __future__ import annotations

from pathlib import Path

from story.runtime import (
    compute_standard_paths,
    resolve_assets_root_for_module,
    resolve_common_package_assets_root,
    resolve_project_root as _resolve_project_root,
)

_PATHS = compute_standard_paths(__file__)
PACKAGE_ROOT = _PATHS["PACKAGE_ROOT"]
PROJECT_ROOT = _PATHS["PROJECT_ROOT"]
PACKAGE_ASSETS_ROOT = _PATHS["PACKAGE_ASSETS_ROOT"]
COMMON_PACKAGE_ASSETS_ROOT = _PATHS["COMMON_PACKAGE_ASSETS_ROOT"]
PROJECT_ASSETS_ROOT = _PATHS["PROJECT_ASSETS_ROOT"]
ASSETS_ROOT = _PATHS["ASSETS_ROOT"]
TESTS_ROOT = _PATHS["TESTS_ROOT"]


def resolve_project_root(preferred: Path | None = None) -> Path:
    return _resolve_project_root(__file__, preferred=preferred)


def resolve_assets_root(project_root: Path | None = None) -> Path:
    return resolve_assets_root_for_module(__file__, project_root=project_root)


def resolve_modes_root(project_root: Path | None = None) -> Path:
    return (resolve_assets_root(project_root) / "modes").resolve()


def resolve_presets_root(project_root: Path | None = None) -> Path:
    return (resolve_assets_root(project_root) / "presets").resolve()


def default_profile_root(project_root: Path | None = None) -> Path:
    return (resolve_assets_root(project_root) / "profiles").resolve()


def resolve_asset_reference(reference: str | Path, project_root: Path | None = None) -> Path:
    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate.resolve()

    root = resolve_project_root(project_root)
    assets_root = resolve_assets_root(root)

    normalized = candidate.as_posix().strip()
    attempts: list[Path] = []

    attempts.append((root / candidate).resolve())
    attempts.append((assets_root / candidate).resolve())

    if normalized.startswith("assets/"):
        stripped = normalized.split("/", 1)[1]
        attempts.append((assets_root / stripped).resolve())
    if normalized.startswith("generator_story/assets/"):
        stripped = normalized.split("generator_story/assets/", 1)[1]
        attempts.append((assets_root / stripped).resolve())

    bundled_assets_root = resolve_common_package_assets_root(__file__)
    if bundled_assets_root != assets_root:
        attempts.append((bundled_assets_root / candidate).resolve())
        if normalized.startswith("assets/"):
            stripped = normalized.split("/", 1)[1]
            attempts.append((bundled_assets_root / stripped).resolve())

    seen: set[Path] = set()
    for attempt in attempts:
        if attempt in seen:
            continue
        seen.add(attempt)
        if attempt.exists():
            return attempt
    return attempts[0]


DEFAULT_PROFILE_ROOT = default_profile_root()
PACKAGE_PROFILE_ROOT = DEFAULT_PROFILE_ROOT
