from __future__ import annotations

from pathlib import Path

_SOURCE_MARKERS = ("pyproject.toml", "image")


def resolve_project_root(module_file: str | Path, preferred: Path | None = None) -> Path:
    """Resolve a source checkout while defaulting to Image's installation root."""
    package = package_root(module_file)
    candidates = [Path(preferred).resolve()] if preferred is not None else []
    candidates.extend((package.parent.resolve(), Path.cwd().resolve()))
    for candidate in candidates:
        if all((candidate / marker).exists() for marker in _SOURCE_MARKERS):
            return candidate
    return package.parent.resolve()


def package_root(module_file: str | Path | None = None) -> Path:
    if module_file is None:
        return Path(__file__).resolve().parent
    module_path = Path(module_file).resolve()
    for candidate in (module_path.parent, *module_path.parents):
        if candidate.name == "image" and (candidate / "__init__.py").is_file():
            return candidate
    return Path(__file__).resolve().parent


def resolve_image_assets_root(module_file: str | Path | None = None) -> Path:
    root = package_root(module_file)
    return (root / "assets").resolve()


def compute_image_standard_paths(module_file: str | Path) -> dict[str, Path]:
    root = package_root(module_file)
    project_root = resolve_project_root(module_file)
    assets_root = resolve_image_assets_root(module_file)
    return {
        "PACKAGE_ROOT": root,
        "PROJECT_ROOT": project_root,
        "PACKAGE_ASSETS_ROOT": assets_root,
        "BUNDLED_ASSETS_ROOT": assets_root,
        "PROJECT_ASSETS_ROOT": assets_root,
        "ASSETS_ROOT": assets_root,
        "TESTS_ROOT": project_root / "tests",
        "PACKAGE_PROFILE_ROOT": (assets_root / "profiles").resolve(),
    }
