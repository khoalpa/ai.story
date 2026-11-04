"""Validate one or every registered reference dataset."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio.reference_samples import (  # noqa: E402
    REFERENCE_DATASET_FILE,
    REFERENCE_REGISTRY_FILE,
    REFERENCE_ROOT,
    ReferenceDataset,
    discover_reference_datasets,
    get_reference_dataset,
    validate_reference_dataset,
)


def check_tracked_dataset(dataset: ReferenceDataset) -> None:
    required = {
        (REFERENCE_ROOT / REFERENCE_REGISTRY_FILE).relative_to(ROOT).as_posix(),
        (dataset.directory / REFERENCE_DATASET_FILE).relative_to(ROOT).as_posix(),
    }
    required.update((dataset.directory / name).relative_to(ROOT).as_posix() for name in dataset.package_names)
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "samples"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=30,
    )
    missing = required - set(result.stdout.split("\0"))
    if missing:
        raise ValueError("Reference data is not tracked by Git: " + ", ".join(sorted(missing)))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--set", dest="set_id", help="Validate one reference set by stable ID")
    choice.add_argument("--all", action="store_true", help="Validate every enabled reference set")
    parser.add_argument("--require-tracked", action="store_true", help="Require registry, manifest and archives in Git")
    args = parser.parse_args()
    try:
        datasets = discover_reference_datasets() if args.all else (get_reference_dataset(args.set_id),)
        failed = False
        for dataset in datasets:
            if args.require_tracked:
                check_tracked_dataset(dataset)
            result = validate_reference_dataset(dataset)
            print(f"{result['status']} {dataset.set_id}: {dataset.title}")
            for error in result["errors"]:
                print(f"  - {error}", file=sys.stderr)
            failed = failed or result["status"] != "PASS"
        return 1 if failed else 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Reference sample check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
