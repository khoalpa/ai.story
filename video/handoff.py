from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1


def _resolve(manifest: Path, raw: object) -> Path | None:
    if not raw:
        return None
    path = Path(str(raw))
    return path.resolve() if path.is_absolute() else (manifest.parent / path).resolve()


def _read(manifest_path: Path, kind: str) -> dict[str, object]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION or data.get("kind") != kind:
        raise ValueError(f"Expected {kind} schema version 1")
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
    artifacts = _read(manifest_path, "audio.video-handoff")
    audio = _resolve(manifest_path, artifacts.get("audio"))
    if audio is None:
        raise ValueError("Audio video handoff is missing artifacts.audio")
    return AudioVideoHandoff(audio, _resolve(manifest_path, artifacts.get("subtitle")))


def read_image_handoff(manifest_path: Path) -> ImageVideoHandoff:
    manifest_path = manifest_path.resolve()
    artifacts = _read(manifest_path, "image.video-handoff")
    scenes = _resolve(manifest_path, artifacts.get("scenes"))
    if scenes is None:
        raise ValueError("Image video handoff is missing artifacts.scenes")
    return ImageVideoHandoff(_resolve(manifest_path, artifacts.get("cover")), scenes)
