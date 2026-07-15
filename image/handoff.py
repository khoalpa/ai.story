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
class StoryImageHandoff:
    manifest_path: Path
    prompt_dir: Path


def read_story_handoff(manifest_path: Path) -> StoryImageHandoff:
    manifest_path = manifest_path.resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION or data.get("kind") != "story.image-handoff":
        raise ValueError("Expected story.image-handoff schema version 1")
    artifact = (data.get("artifacts") or {}).get("prompt_dir")
    if not artifact:
        raise ValueError("Story image handoff is missing artifacts.prompt_dir")
    return StoryImageHandoff(manifest_path, _resolve(manifest_path, artifact))


def write_video_handoff(manifest_path: Path, *, cover: Path | None, scenes: Path) -> Path:
    manifest_path = manifest_path.resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {"scenes": _relative(manifest_path, scenes)}
    if cover is not None:
        artifacts["cover"] = _relative(manifest_path, cover)
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
