from __future__ import annotations

import json
import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1


def _resolve(manifest: Path, raw: object) -> Path | None:
    descriptor = raw if isinstance(raw, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("path")
    if not raw:
        return None
    path = Path(str(raw))
    resolved = path.resolve() if path.is_absolute() else (manifest.parent / path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Handoff artifact not found in {manifest}: {resolved}")
    if descriptor:
        expected_type = descriptor.get("media_type")
        actual_type = "inode/directory" if resolved.is_dir() else (mimetypes.guess_type(resolved.name)[0] or "application/octet-stream")
        if expected_type and expected_type != actual_type:
            raise ValueError(
                f"Artifact media type mismatch in {manifest}: {resolved} "
                f"declares {expected_type}, detected {actual_type}"
            )
        expected_size = descriptor.get("size_bytes")
        if expected_size is not None and resolved.is_file() and resolved.stat().st_size != expected_size:
            raise ValueError(f"Artifact size mismatch in {manifest}: {resolved}")
    if descriptor and descriptor.get("sha256") and resolved.is_file():
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual != descriptor["sha256"]:
            raise ValueError(f"Artifact checksum mismatch: {resolved}")
    return resolved


def _read(manifest_path: Path, kind: str, producer: str) -> dict[str, object]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Handoff manifest root must be an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Expected {kind} schema version 1")
    if data.get("kind") != kind:
        raise ValueError(f"Expected handoff kind {kind}")
    if data.get("producer") != producer:
        raise ValueError(f"Expected producer {producer}")
    if not data.get("created_at"):
        raise ValueError("Handoff manifest is missing created_at")
    return dict(data.get("artifacts") or {})


@dataclass(frozen=True)
class AudioVideoHandoff:
    audio: Path
    subtitle: Path | None


@dataclass(frozen=True)
class ImageVideoHandoff:
    cover: Path | None
    scenes: Path


def read_audio_handoff(manifest_path: Path) -> AudioVideoHandoff:
    manifest_path = manifest_path.resolve()
    artifacts = _read(manifest_path, "audio.video-handoff", "audio")
    audio = _resolve(manifest_path, artifacts.get("audio"))
    if audio is None:
        raise ValueError("Audio video handoff is missing artifacts.audio")
    if not audio.is_file() or audio.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
        raise ValueError(f"Unsupported audio artifact in {manifest_path}: {audio}")
    return AudioVideoHandoff(audio, _resolve(manifest_path, artifacts.get("subtitle")))


def read_image_handoff(manifest_path: Path) -> ImageVideoHandoff:
    manifest_path = manifest_path.resolve()
    artifacts = _read(manifest_path, "image.video-handoff", "image")
    scenes = _resolve(manifest_path, artifacts.get("scenes"))
    if scenes is None:
        raise ValueError("Image video handoff is missing artifacts.scenes")
    if not scenes.is_dir():
        raise ValueError(f"Scenes artifact is not a directory in {manifest_path}: {scenes}")
    return ImageVideoHandoff(_resolve(manifest_path, artifacts.get("cover")), scenes)
