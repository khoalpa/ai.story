from __future__ import annotations

import json
import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

SCHEMA_VERSION = 1


def write_handoff(manifest_path: Path, *, kind: str, artifacts: Mapping[str, Path | str]) -> Path:
    if kind not in {"story.audio-handoff", "story.image-handoff"}:
        raise ValueError(f"Unsupported Story handoff kind: {kind}")
    manifest_path = manifest_path.resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, object] = {}
    for name, value in artifacts.items():
        path = Path(value)
        if path.is_absolute():
            try:
                path = path.resolve().relative_to(manifest_path.parent)
            except ValueError:
                path = path.resolve()
        absolute = (manifest_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
        resolved[name] = _describe_artifact(path.as_posix(), absolute)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "producer": "story",
        "artifacts": resolved,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _describe_artifact(relative_path: str, absolute: Path) -> dict[str, object]:
    descriptor: dict[str, object] = {
        "path": relative_path,
        "media_type": "inode/directory" if absolute.is_dir() else (mimetypes.guess_type(absolute.name)[0] or "application/octet-stream"),
    }
    if absolute.is_file():
        payload = absolute.read_bytes()
        descriptor.update(size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    return descriptor
