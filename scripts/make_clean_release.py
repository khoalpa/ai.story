from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
TMP = OUT / 'audio_story_project_clean'
ZIP_BASE = OUT / 'audio_story_project_clean_release'

EXCLUDE_DIR_NAMES = {
    '.git', '.idea', '.vscode', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    'dist', 'build', '.eggs', '.tox', '.nox', '.venv', 'venv', 'node_modules',
}
EXCLUDE_FILE_SUFFIXES = {'.pyc', '.pyo'}
EXCLUDE_FILE_NAMES = {'.DS_Store', 'Thumbs.db'}
EXCLUDE_RELATIVE_PARTS = {
    ('tests',),
    ('packages', 'audio', 'tests'),
    ('packages', 'story', 'tests'),
    ('packages', 'video', 'tests'),
    ('packages', 'audio', 'out'),
    ('packages', 'video', 'out'),
}
EXCLUDE_EXACT_FILES: set[tuple[str, ...]] = set()


def should_skip(rel: Path) -> bool:
    parts = rel.parts
    if not parts:
        return False
    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True
    if tuple(parts) in EXCLUDE_EXACT_FILES:
        return True
    for excluded in EXCLUDE_RELATIVE_PARTS:
        if parts[:len(excluded)] == excluded:
            return True
    if rel.name in EXCLUDE_FILE_NAMES:
        return True
    if rel.suffix in EXCLUDE_FILE_SUFFIXES:
        return True
    if any(part.endswith('.egg-info') or part.endswith('.dist-info') for part in parts):
        return True
    return False


def main() -> None:
    OUT.mkdir(exist_ok=True)
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)

    for src in ROOT.rglob('*'):
        rel = src.relative_to(ROOT)
        if should_skip(rel):
            continue
        dst = TMP / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    archive = shutil.make_archive(str(ZIP_BASE), 'zip', root_dir=TMP)
    print(archive)


if __name__ == '__main__':
    main()
