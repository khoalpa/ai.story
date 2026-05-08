from __future__ import annotations

import importlib
import platform
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ok: bool
    version: str
    detail: str = ""


def _module_version(module: Any) -> str:
    value = getattr(module, "__version__", None)
    if value is None:
        return "unknown"
    return str(value)


def collect_runtime_diagnostics() -> dict[str, Any]:
    dependencies: list[DependencyStatus] = []
    for name in ("yaml", "requests", "streamlit"):
        try:
            mod = importlib.import_module(name)
            dependencies.append(DependencyStatus(name=name, ok=True, version=_module_version(mod)))
        except Exception as exc:
            dependencies.append(DependencyStatus(name=name, ok=False, version="missing", detail=str(exc)))

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "executable": sys.executable,
        "dependencies": [
            {
                "name": dep.name,
                "ok": dep.ok,
                "version": dep.version,
                "detail": dep.detail,
            }
            for dep in dependencies
        ],
    }
