from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audio.model_store import (
    format_size,
    models_root,
    prune_empty_model_directories,
    remove_model_store_path,
    scan_model_store,
)

MODULE_FILES = {
    "audio": ROOT / "audio" / "__init__.py",
    "story": ROOT / "story" / "__init__.py",
    "image": ROOT / "image" / "__init__.py",
    "video": ROOT / "video" / "__init__.py",
}


def _selected_modules(value: str) -> list[str]:
    selected = str(value or "all").strip().lower()
    if selected == "all":
        return list(MODULE_FILES)
    return [selected]


def _module_file(module: str) -> Path:
    return MODULE_FILES[module]


def _print_report(*, module: str, include_cache: bool, max_depth: int, as_json: bool) -> None:
    report = scan_model_store(_module_file(module), include_cache=include_cache, max_depth=max_depth)
    if as_json:
        payload = report.as_dict()
        payload["module"] = module
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"Module: {module}")
    print(f"Models root: {report.root}")
    print(
        "Total: "
        f"{format_size(report.size_bytes)} | "
        f"{report.file_count} file(s) | "
        f"{report.directory_count} dir(s)"
    )
    if not report.entries:
        print("No local models found.")
        return

    for entry in report.entries:
        print(
            f"- {entry.relative_path} "
            f"[{entry.kind}] "
            f"{format_size(entry.size_bytes)} "
            f"({entry.file_count} file(s), {entry.directory_count} dir(s))"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect and manage module-local model stores.")
    parser.add_argument(
        "--module",
        choices=[*MODULE_FILES.keys(), "all"],
        default="all",
        help="Module model store to inspect. Defaults to all modules.",
    )
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List local model store entries.")
    list_parser.add_argument("--no-cache", action="store_true", help="Hide local_models/_cache entries.")
    list_parser.add_argument("--max-depth", type=int, default=2, help="Maximum path depth to list.")
    list_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    subparsers.add_parser("path", help="Print the resolved module-local models root.")

    prune_parser = subparsers.add_parser("prune-empty", help="Remove empty directories under local_models/.")
    prune_parser.add_argument("--apply", action="store_true", help="Delete empty directories. Without this flag, only prints a dry run.")

    remove_parser = subparsers.add_parser("remove", help="Remove one model/cache path relative to a module local_models/.")
    remove_parser.add_argument("relative_path", help="Path relative to local_models/, for example vieneu/model.gguf.")
    remove_parser.add_argument("--apply", action="store_true", help="Delete the path. Without this flag, only prints a dry run.")

    parser.set_defaults(command="list")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    modules = _selected_modules(args.module)
    if args.command == "path":
        for module in modules:
            print(f"{module}: {models_root(_module_file(module))}")
        return 0

    if args.command == "prune-empty":
        action = "Removed" if args.apply else "Would remove"
        for module in modules:
            paths = prune_empty_model_directories(_module_file(module), apply=args.apply)
            print(f"{action} {len(paths)} empty directorie(s) for {module}.")
            for path in paths:
                print(f"- {path}")
        if not args.apply:
            print("Dry run only. Re-run with --apply to delete these directories.")
        return 0

    if args.command == "remove":
        if args.module == "all":
            print("The remove command requires --module audio|story|image|video.", file=sys.stderr)
            return 2
        target = remove_model_store_path(args.relative_path, _module_file(modules[0]), apply=args.apply)
        action = "Removed" if args.apply else "Would remove"
        print(f"{action}: {target}")
        if not args.apply:
            print("Dry run only. Re-run with --apply to delete this path.")
        return 0

    if bool(args.json) and len(modules) > 1:
        reports = []
        for module in modules:
            report = scan_model_store(_module_file(module), include_cache=not bool(args.no_cache), max_depth=max(1, int(args.max_depth)))
            payload = report.as_dict()
            payload["module"] = module
            reports.append(payload)
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 0
    for index, module in enumerate(modules):
        if index:
            print()
        _print_report(
            module=module,
            include_cache=not bool(args.no_cache),
            max_depth=max(1, int(args.max_depth)),
            as_json=bool(args.json),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
