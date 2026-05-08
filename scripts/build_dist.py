from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import build_meta as backend

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"


class BuildFailure(RuntimeError):
    pass


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    if BUILD.exists():
        shutil.rmtree(BUILD)
    DIST.mkdir(parents=True, exist_ok=True)

    print("Building sdist...")
    sdist_name = backend.build_sdist(str(DIST))
    print(f"- {sdist_name}")

    print("Building wheel...")
    wheel_name = backend.build_wheel(str(DIST))
    print(f"- {wheel_name}")

    built = sorted(p.name for p in DIST.iterdir() if p.is_file())
    expected = {sdist_name, wheel_name}
    missing = expected.difference(built)
    if missing:
        raise BuildFailure(f"Missing expected release artifacts in dist/: {sorted(missing)}")

    print("Artifacts:")
    for name in built:
        print(f"- {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
