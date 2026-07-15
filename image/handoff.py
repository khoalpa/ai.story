from __future__ import annotations

import json
import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def _resolve(manifest: Path, raw: object) -> Path:
    descriptor = raw if isinstance(raw, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("path")
    path = Path(str(raw or ""))
    resolved = path.resolve() if path.is_absolute() else (manifest.parent / path).resolve()
    if descriptor and descriptor.get("sha256") and resolved.is_file():
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != descriptor["sha256"]:
            raise ValueError(f"Artifact checksum mismatch: {resolved}")
    return resolved


@dataclass(frozen=True)
class StoryImageHandoff:
    manifest_path: Path
    prompt_dir: Path


def read_story_handoff(manifest_path: Path) -> StoryImageHandoff:
    manifest_path = manifest_path.resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_envelope(data, "story.image-handoff", "story")
    artifact = (data.get("artifacts") or {}).get("prompt_dir")
    if not artifact:
        raise ValueError("Story image handoff is missing artifacts.prompt_dir")
    return StoryImageHandoff(manifest_path, _resolve(manifest_path, artifact))


def _validate_envelope(data: object, kind: str, producer: str) -> None:
    if not isinstance(data, dict):
        raise ValueError("Handoff manifest root must be an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Expected {kind} schema version {SCHEMA_VERSION}")
    if data.get("kind") != kind:
        raise ValueError(f"Expected handoff kind {kind}")
    if data.get("producer") != producer:
        raise ValueError(f"Expected producer {producer}")
    if not data.get("created_at"):
        raise ValueError("Handoff manifest is missing created_at")


def write_video_handoff(manifest_path: Path, *, cover: Path | None, scenes: Path) -> Path:
    manifest_path = manifest_path.resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {"scenes": _describe(manifest_path, scenes)}
    if cover is not None:
        artifacts["cover"] = _describe(manifest_path, cover)
    payload = {"schema_version": SCHEMA_VERSION, "kind": "image.video-handoff",
               "created_at": datetime.now(timezone.utc).isoformat(), "producer": "image",
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
        "media_type": "inode/directory" if path.is_dir() else (mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
    }
    if path.is_file():
        result.update(size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    return result
