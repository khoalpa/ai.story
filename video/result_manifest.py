from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 1


def _describe(manifest: Path, path: Path) -> dict[str, object]:
    path = path.resolve()
    try:
        stored_path = path.relative_to(manifest.parent).as_posix()
    except ValueError:
        stored_path = path.as_posix()
    payload = path.read_bytes()
    return {
        "path": stored_path,
        "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def write_result_manifest(
    manifest_path: Path,
    *,
    video: Path,
    input_manifests: Iterable[Path] = (),
    duration_seconds: float | None = None,
    resolution: str | None = None,
) -> Path:
    """Write the stable output contract for a completed Video render."""
    manifest_path = manifest_path.resolve()
    video = video.resolve()
    if not video.is_file():
        raise FileNotFoundError(f"Rendered video not found: {video}")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, object] = {}
    if duration_seconds is not None:
        metadata["duration_seconds"] = duration_seconds
    if resolution:
        metadata["resolution"] = resolution
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "video.result-manifest",
        "producer": "video",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {"video": _describe(manifest_path, video)},
        "metadata": metadata,
        "provenance": {
            "input_manifests": [str(path.resolve()) for path in input_manifests],
        },
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
