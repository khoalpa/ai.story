"""Migrate the active Stage 4 directory to source-bound native voice prompts."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from studio.video_prompt_validation import canonical_output_digest
from studio.video_voice import build_voice_plan, default_voice_strategy, native_audio_prompt
from studio.workflow_package import package_digest


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def migrate(root: Path) -> None:
    story_path = root / "story.json"
    plan_path = root / "video_prompts.json"
    manifest_path = root / "workflow_manifest.json"
    story = json.loads(story_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    script = story["script"]
    strategy = default_voice_strategy()

    target = plan["generator_target"]
    target["capability_profile"]["audio_mode"] = "NATIVE_DIALOGUE"
    migrated: dict[str, object] = {}
    for key, value in plan.items():
        migrated[key] = value
        if key == "project":
            migrated["voice_strategy"] = strategy
    for clip in migrated["clips"]:  # type: ignore[index]
        source = clip["source_script"]
        voice_plan = build_voice_plan(script, source)
        ambience = str(clip["audio_prompt"])
        updated: dict[str, object] = {}
        for key, value in clip.items():
            updated[key] = value
            if key == "prompt":
                updated["voice_plan"] = voice_plan
        updated["audio_prompt"] = native_audio_prompt(voice_plan, strategy, ambience)
        clip.clear()
        clip.update(updated)
    migrated["validation"]["output_digest_sha256"] = canonical_output_digest(migrated)  # type: ignore[index]
    plan_raw = encoded(migrated)

    row = next(item for item in manifest["files"] if item["path"] == "video_prompts.json")
    row["sha256"] = hashlib.sha256(plan_raw).hexdigest()
    row["size_bytes"] = len(plan_raw)
    manifest["package_digest_sha256"] = package_digest(manifest["files"])
    manifest_raw = encoded(manifest)

    backup = Path(__file__).resolve().parents[1] / "tmp" / "native_voice_migration_backup"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plan_path, backup / "video_prompts.json")
    shutil.copy2(manifest_path, backup / "workflow_manifest.json")
    plan_path.write_bytes(plan_raw)
    manifest_path.write_bytes(manifest_raw)


if __name__ == "__main__":
    migrate(Path(r"D:\project\ai.story\output"))
