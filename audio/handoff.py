from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def _resolve(manifest: Path, raw: object) -> Path:
    path = Path(str(raw or ""))
    return path.resolve() if path.is_absolute() else (manifest.parent / path).resolve()


@dataclass(frozen=True)
class StoryAudioHandoff:
    manifest_path: Path
    plain_script: Path


def read_story_handoff(manifest_path: Path) -> StoryAudioHandoff:
    manifest_path = manifest_path.resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION or data.get("kind") != "story.audio-handoff":
        raise ValueError("Expected story.audio-handoff schema version 1")
    artifact = (data.get("artifacts") or {}).get("plain_script")
    if not artifact:
        raise ValueError("Story audio handoff is missing artifacts.plain_script")
    return StoryAudioHandoff(manifest_path, _resolve(manifest_path, artifact))


def write_video_handoff(manifest_path: Path, *, audio: Path, subtitle: Path | None = None) -> Path:
    manifest_path = manifest_path.resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {"audio": _relative(manifest_path, audio)}
    if subtitle is not None:
        artifacts["subtitle"] = _relative(manifest_path, subtitle)
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
