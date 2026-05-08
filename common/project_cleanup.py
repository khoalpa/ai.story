from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


CACHE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
BUILD_DIR_NAMES = {
    "build",
    "dist",
    "htmlcov",
    "site",
}
VENV_DIR_NAMES = {
    ".venv",
    "venv",
    "env",
    "ENV",
}
RUNTIME_DIR_NAMES = {
    ".render_audio_gui",
    "out",
    "output",
    "tmp",
}
RUNTIME_DIR_PREFIXES = (
    "tmp",
    ".tmp_test_",
)
TOOL_LOG_FILE_NAMES = {
    "npm-debug.log",
    "yarn-debug.log",
    "yarn-error.log",
    "pip-log.txt",
}
REMOVABLE_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".out",
    ".err",
}
REMOVABLE_FILE_NAMES = {
    ".coverage",
    ".DS_Store",
    "Thumbs.db",
}


@dataclass(frozen=True)
class CleanupPlan:
    files: tuple[Path, ...]
    directories: tuple[Path, ...]

    @property
    def count(self) -> int:
        return len(self.files) + len(self.directories)


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def is_runtime_dir_name(name: str) -> bool:
    return name in RUNTIME_DIR_NAMES or any(name.startswith(prefix) for prefix in RUNTIME_DIR_PREFIXES)


def is_build_dir_name(name: str) -> bool:
    return name in BUILD_DIR_NAMES or name.endswith(".egg-info") or name.endswith(".dist-info")


def is_removable_file(path: Path) -> bool:
    return path.name in TOOL_LOG_FILE_NAMES or path.name in REMOVABLE_FILE_NAMES or path.suffix in REMOVABLE_FILE_SUFFIXES


def dedupe_nested_directories(paths: set[Path]) -> tuple[Path, ...]:
    ordered = sorted(paths, key=lambda path: (len(path.parts), str(path).lower()))
    selected: list[Path] = []
    for path in ordered:
        if any(is_relative_to(path, parent) for parent in selected):
            continue
        selected.append(path)
    return tuple(selected)


def build_cleanup_plan(
    root: Path,
    *,
    include_runtime: bool = False,
    include_venv: bool = False,
    include_models: bool = False,
) -> CleanupPlan:
    root = root.resolve()
    directories: set[Path] = set()
    files: set[Path] = set()

    for path in root.rglob("*"):
        resolved = path.resolve()
        if not is_relative_to(resolved, root):
            continue
        rel = resolved.relative_to(root)
        top = rel.parts[0] if rel.parts else ""
        if top == "models" and not include_models:
            continue
        if is_runtime_dir_name(top) and not include_runtime:
            continue
        if top in VENV_DIR_NAMES and not include_venv:
            continue

        if path.is_dir():
            name = path.name
            if name in CACHE_DIR_NAMES or is_build_dir_name(name):
                directories.add(resolved)
            elif include_runtime and is_runtime_dir_name(name):
                directories.add(resolved)
            elif include_venv and name in VENV_DIR_NAMES:
                directories.add(resolved)
            elif include_models and resolved == root / "models":
                directories.add(resolved)
        elif path.is_file() and is_removable_file(path):
            files.add(resolved)

    directories_tuple = dedupe_nested_directories(directories)
    files_tuple = tuple(sorted(
        path for path in files if not any(is_relative_to(path, directory) for directory in directories_tuple)
    ))
    return CleanupPlan(files=files_tuple, directories=directories_tuple)


def apply_cleanup_plan(plan: CleanupPlan) -> None:
    for file_path in plan.files:
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass

    for directory in sorted(plan.directories, key=lambda path: len(path.parts), reverse=True):
        try:
            shutil.rmtree(directory)
        except FileNotFoundError:
            pass
