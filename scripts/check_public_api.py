from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SNAPSHOT = ROOT / "public_api_snapshot.json"


def main() -> int:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    failures: list[str] = []
    for module_name, symbols in expected.items():
        module = importlib.import_module(module_name)
        missing = [symbol for symbol in symbols if not hasattr(module, symbol)]
        if missing:
            failures.append(f"{module_name}: missing {', '.join(missing)}")
    if failures:
        raise SystemExit("Public API compatibility check failed:\n" + "\n".join(failures))
    print(f"Public API snapshot passed for {len(expected)} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
