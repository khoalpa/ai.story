from __future__ import annotations

from pathlib import Path

from common.runtime import resolve_project_root


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
        "COMMON_PACKAGE_ASSETS_ROOT": assets_root,
        "PROJECT_ASSETS_ROOT": assets_root,
        "ASSETS_ROOT": assets_root,
        "TESTS_ROOT": project_root / "tests",
        "PACKAGE_PROFILE_ROOT": (assets_root / "profiles").resolve(),
    }
