#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "package_api_policy.json").read_text(encoding="utf-8"))
PACKAGES = {"audio", "story", "image", "video"}
DIRECTION = POLICY["dependency_direction"]
IGNORE_TESTS = POLICY.get("rules", {}).get("ignore_tests_for_dependency_direction", True)

def iter_python_files():
    for path in ROOT.rglob("*.py"):
        if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        yield path

def imported_top_modules(node):
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return [node.module.split(".")[0]]
    return []

def main() -> int:
    errors: list[str] = []
    for path in iter_python_files():
        rel = path.relative_to(ROOT)
        parts = rel.parts
        current = parts[0] if parts and parts[0] in PACKAGES else None
        if current is None:
            continue
        if IGNORE_TESTS and parts[0] == "tests":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append(f"{rel}: syntax error during dependency check: {exc}")
            continue

        allowed = set(DIRECTION.get(current, [])) | {current}
        for node in ast.walk(tree):
            for top in imported_top_modules(node):
                if top not in PACKAGES:
                    continue
                if top not in allowed:
                    errors.append(
                        f"{rel}:{getattr(node, 'lineno', '?')} imports '{top}', "
                        f"but package '{current}' may only depend on {sorted(allowed)}"
                    )

    if errors:
        print("Dependency direction check failed:\n")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Dependency direction check passed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
