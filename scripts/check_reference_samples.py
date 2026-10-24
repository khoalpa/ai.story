"""Fail early when CI is missing or using modified reference story archives."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio.reference_samples import (  # noqa: E402
    REFERENCE_CHECKSUM_FILE,
    REFERENCE_PACKAGE_DIRECTORY,
    REFERENCE_PACKAGE_NAMES,
    load_reference_package,
)


def check_tracked_samples() -> None:
    relative = REFERENCE_PACKAGE_DIRECTORY.relative_to(ROOT)
    required = {(relative / name).as_posix() for name in (*REFERENCE_PACKAGE_NAMES, REFERENCE_CHECKSUM_FILE)}
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", relative.as_posix()], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=30,
    )
    missing = required - set(result.stdout.split("\0"))
    if missing:
        raise ValueError("Reference data is not tracked by Git: " + ", ".join(sorted(missing)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-tracked", action="store_true", help="Also require all reference inputs in the Git index")
    args = parser.parse_args()
    try:
        if args.require_tracked:
            check_tracked_samples()
        for name in REFERENCE_PACKAGE_NAMES:
            _members, result = load_reference_package(name)
            print(f"PASS {name}: SHA-256, {result['stage']}, schema and payload checks")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Reference sample check failed: {exc}", file=sys.stderr)
        return 1
    print("All four reference archives are ready; output/ is not required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
