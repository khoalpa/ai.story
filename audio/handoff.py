from __future__ import annotations

import json
import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def write_video_handoff(
    manifest_path: Path,
    *,
    audio: Path,
    subtitle: Path | None = None,
    quality_report: Path | None = None,
) -> Path:
    manifest_path = manifest_path.resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {"audio": _describe(manifest_path, audio)}
    if subtitle is not None:
        artifacts["subtitle"] = _describe(manifest_path, subtitle)
    if quality_report is None:
        candidate = audio.with_name(f"{audio.stem}.audio_quality.json")
        quality_report = candidate if candidate.is_file() else None
    if quality_report is not None and quality_report.is_file():
        artifacts["quality_report"] = _describe(manifest_path, quality_report)
    payload = {"schema_version": SCHEMA_VERSION, "kind": "audio.video-handoff",
               "created_at": datetime.now(timezone.utc).isoformat(), "producer": "audio",
               "artifacts": artifacts}
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _relative(manifest: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(manifest.parent).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _describe(manifest: Path, path: Path) -> dict[str, object]:
    payload = path.read_bytes() if path.is_file() else b""
    result: dict[str, object] = {
        "path": _relative(manifest, path),
        "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }
    if path.is_file():
        result.update(size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    return result
