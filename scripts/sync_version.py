from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
TARGETS = [
    ROOT / "audio" / "__init__.py",
    ROOT / "story" / "__init__.py",
    ROOT / "video" / "__init__.py",
    ROOT / "pyproject.toml",
]


def read_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?", version):
        raise SystemExit(f"Invalid version in {VERSION_FILE}: {version!r}")
    return version


def replace_exact(path: Path, pattern: str, repl: str) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, repl, text, flags=re.MULTILINE)
    if count:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> int:
    version = read_version()
    changed: list[str] = []

    for path in TARGETS:
        if not path.exists():
            raise SystemExit(f"Missing target for version sync: {path}")
        if path.name == 'pyproject.toml':
            ok = replace_exact(path, r'^version\s*=\s*"[^"]+"$', f'version = "{version}"')
        else:
            ok = replace_exact(path, r'^__version__\s*=\s*"[^"]+"$', f'__version__ = "{version}"')
        if not ok:
            raise SystemExit(f'Could not sync version in {path}')
        changed.append(str(path.relative_to(ROOT)))

    print(f"Synced version {version} from {VERSION_FILE.name}")
    for item in changed:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
