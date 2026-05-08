from __future__ import annotations

from pathlib import Path
from typing import Callable

_SOURCE_MARKERS = ("pyproject.toml", "story", "audio", "image", "video", "common")
_LEGACY_SOURCE_ASSETS_DIRNAME = "assets"
_SOURCE_COMMON_ASSETS_RELATIVE = Path("common") / "assets"


def _common_package_root() -> Path:
    return Path(__file__).resolve().parent


def resolve_common_package_assets_root(module_file: str | Path | None = None) -> Path:
    if module_file is not None:
        module_path = Path(module_file).resolve()
        sibling_common_assets = (module_path.parent.parent / "common" / "assets").resolve()
        if sibling_common_assets.is_dir():
            return sibling_common_assets
    return (_common_package_root() / "assets").resolve()


def _source_common_assets_root(path: Path) -> Path:
    return (path / _SOURCE_COMMON_ASSETS_RELATIVE).resolve()


def _legacy_source_assets_root(path: Path) -> Path:
    return (path / _LEGACY_SOURCE_ASSETS_DIRNAME).resolve()


def _looks_like_source_checkout(path: Path) -> bool:
    return all((path / marker).exists() for marker in _SOURCE_MARKERS)


def resolve_project_root(module_file: str | Path, preferred: Path | None = None) -> Path:
    package_root = Path(module_file).resolve().parent
    default_project_root = package_root.parent.resolve()
    candidates: list[Path] = []
    if preferred is not None:
        candidates.append(Path(preferred).resolve())
    candidates.append(default_project_root)

    cwd = Path.cwd().resolve()
    try:
        package_root.relative_to(cwd)
    except ValueError:
        pass
    else:
        candidates.append(cwd)

    for candidate in candidates:
        if _looks_like_source_checkout(candidate):
            return candidate
    return default_project_root


def resolve_assets_root_for_module(module_file: str | Path, project_root: Path | None = None) -> Path:
    project = resolve_project_root(module_file, preferred=project_root)
    source_common_assets = _source_common_assets_root(project)
    if _looks_like_source_checkout(project) and source_common_assets.is_dir():
        return source_common_assets

    legacy_source_assets = _legacy_source_assets_root(project)
    if _looks_like_source_checkout(project) and legacy_source_assets.is_dir():
        return legacy_source_assets

    bundled_assets = resolve_common_package_assets_root(module_file)
    if bundled_assets.is_dir():
        return bundled_assets

    package_root = Path(module_file).resolve().parent
    package_assets = (package_root / "assets").resolve()
    if package_assets.is_dir():
        return package_assets

    return bundled_assets


def compute_standard_paths(module_file: str | Path) -> dict[str, Path]:
    package_root = Path(module_file).resolve().parent
    project_root = resolve_project_root(module_file)
    package_assets_root = (package_root / "assets").resolve()
    common_package_assets_root = resolve_common_package_assets_root(module_file)
    project_assets_root = _source_common_assets_root(project_root)
    assets_root = resolve_assets_root_for_module(module_file, project_root=project_root)
    return {
        "PACKAGE_ROOT": package_root,
        "PROJECT_ROOT": project_root,
        "PACKAGE_ASSETS_ROOT": package_assets_root,
        "COMMON_PACKAGE_ASSETS_ROOT": common_package_assets_root,
        "PROJECT_ASSETS_ROOT": project_assets_root,
        "ASSETS_ROOT": assets_root,
        "TESTS_ROOT": project_root / "tests",
        "PACKAGE_PROFILE_ROOT": (assets_root / "profiles").resolve(),
    }


def run_main(main_func: Callable[[], int | None]) -> None:
    result = main_func()
    raise SystemExit(0 if result is None else result)
