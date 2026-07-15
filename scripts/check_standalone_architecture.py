from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ("story", "audio", "image", "video")


def main() -> int:
    errors: list[str] = []
    for retired in (ROOT / "common", ROOT / "studio" / "_shared"):
        if retired.exists():
            errors.append(f"Retired package exists: {retired.relative_to(ROOT)}")

    for package in FEATURES:
        for path in (ROOT / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    top = name.split(".", 1)[0]
                    if top in FEATURES and top != package:
                        errors.append(f"{path.relative_to(ROOT)} imports sibling {top}")

    studio_source = (ROOT / "studio" / "gui_entry.py").read_text(encoding="utf-8")
    for package in FEATURES:
        if f"from {package}.app_api import" not in studio_source:
            errors.append(f"Studio does not integrate {package} through app_api")
        if f"from {package}.gui" in studio_source:
            errors.append(f"Studio imports {package}.gui directly")

    hashes: dict[str, tuple[str, Path]] = {}
    for package in FEATURES:
        assets = ROOT / package / "assets"
        if not assets.is_dir():
            continue
        for path in assets.rglob("*"):
            if not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            previous = hashes.get(digest)
            if previous and previous[0] != package:
                errors.append(
                    f"Cross-package duplicate asset: {previous[1].relative_to(ROOT)} and {path.relative_to(ROOT)}"
                )
            else:
                hashes[digest] = (package, path)

    if errors:
        print("Standalone architecture check failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Standalone architecture check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
