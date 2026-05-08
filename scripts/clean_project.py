from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio._shared.project_cleanup import apply_cleanup_plan, build_cleanup_plan


def _format_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean generated project artifacts.")
    parser.add_argument("--apply", action="store_true", help="Delete matched artifacts. Without this flag, only prints a dry run.")
    parser.add_argument("--include-runtime", action="store_true", help="Also remove runtime outputs such as output/, tmp/, out/, and .render_audio_gui/.")
    parser.add_argument("--include-venv", action="store_true", help="Also remove local virtual environments.")
    parser.add_argument("--include-models", action="store_true", help="Also remove module-local model stores such as audio/models/. This can be very large.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root to clean. Defaults to this repository.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    plan = build_cleanup_plan(
        root,
        include_runtime=args.include_runtime,
        include_venv=args.include_venv,
        include_models=args.include_models,
    )

    action = "Removing" if args.apply else "Would remove"
    print(f"{action} {plan.count} artifact(s) under {root}")
    for directory in plan.directories:
        print(f"- dir  {_format_rel(directory, root)}")
    for file_path in plan.files:
        print(f"- file {_format_rel(file_path, root)}")

    if args.apply:
        apply_cleanup_plan(plan)
        print("Cleanup completed.")
    else:
        print("Dry run only. Re-run with --apply to delete these artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
