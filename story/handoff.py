from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

SCHEMA_VERSION = 1


def write_handoff(manifest_path: Path, *, kind: str, artifacts: Mapping[str, Path | str]) -> Path:
    if kind not in {"story.audio-handoff", "story.image-handoff"}:
        raise ValueError(f"Unsupported Story handoff kind: {kind}")
    manifest_path = manifest_path.resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, str] = {}
    for name, value in artifacts.items():
        path = Path(value)
        if path.is_absolute():
            try:
                path = path.resolve().relative_to(manifest_path.parent)
            except ValueError:
                path = path.resolve()
        resolved[name] = path.as_posix()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "producer": "story",
        "artifacts": resolved,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
