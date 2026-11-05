"""Small synthetic story packages generated only inside test directories."""
from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

ZONES = ("GREETING", "OPENING", "INTRODUCTION", "DEVELOPMENT", "CLIMAX", "FALLING", "ENDING", "FAREWELL")
STEMS = ("cover", "greeting", "opening", "introduction", "development", "climax", "falling", "ending", "farewell", "outro")
ARCHIVES = ("story_stage1.zip", "story_stage2.zip", "story.zip", "story_video_prompts.zip")


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def replace_json(root: Path, name: str, value: Any) -> None:
    """Rebind an edited fixture payload without weakening production checks."""
    raw = encoded(value)
    (root / name).write_bytes(raw)
    manifest = json.loads((root / "manifest.json").read_bytes())
    row = next(row for row in manifest["files"] if row["path"] == name)
    row.update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (root / "manifest.json").write_bytes(encoded(manifest))


def synthetic_story() -> dict[str, Any]:
    return {
        "schema_version": "4.1.3",
        "meta": {"title": "Cánh cửa thử nghiệm", "series": None, "episode": 1,
                 "author": "Test", "channel": "Test", "profile": "ADULT_STANDARD",
                 "age_band": "18+", "language": "vi", "genre": "Đời sống", "tone": "Ấm áp",
                 "target_minutes": 1, "estimated_minutes": 1, "timing_method": "WHITESPACE_RATE_V1", "tags": ["test"]},
        "characters": [{"character_id": f"c{i:03d}", "name": name, "age": 30,
                        "role": "Bạn đồng hành", "appearance": "Áo xanh", "personality": "Điềm tĩnh",
                        "voice_note": "Giọng trung"} for i, name in enumerate(("An", "Bình", "Chi"), 1)],
        "outline": [{"scene_id": "sc001", "summary": "Các bạn mở cửa", "change": "Bước ra ngoài",
                     "setup_or_payoff": "Cánh cửa"},
                    {"scene_id": "sc002", "summary": "Các bạn trở về", "change": "Khép cửa",
                     "setup_or_payoff": "Cánh cửa đã đóng"}],
        "script": [{"id": f"s{i:04d}", "zone": zone, "scene_id": "sc001" if i <= 4 else "sc002", "speaker": "narrator",
                    "text": f"Đoạn kể thử nghiệm thứ {i}.", "emotion": "bình tĩnh", "speed": 1.0,
                    "pause_ms": 100, "ambience": None} for i, zone in enumerate(ZONES, 1)],
    }


def png(size: tuple[int, int]) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, "blue").save(stream, format="PNG")
    return stream.getvalue()


def legacy_files(stage: int) -> dict[str, bytes]:
    story = synthetic_story()
    gates = ("JSON_PARSE", "SCHEMA_LINKS", "FILE_SET", "MANIFEST_MATCH", "CONTENT_SAFETY",
             "STORY_TIMING", "STORY_CRAFT", "VISUAL_PLAN", "IMAGE_FILES", "VIDEO_SPANS")
    report = {
        "schema_version": "4.1.3", "prompt_version": "4.1.6", "stage": stage, "status": "COMPLETE",
        "input_sources": ["Synthetic test input"],
        "checks": [{"id": gate, "status": "PASS", "method": "CODE", "required": True,
                    "target": "package", "details": "Synthetic report for automated tests."} for gate in gates],
        "limitations": [], "remaining_work": [],
        "archive_validation": {"status": "NOT_CHECKED", "details": "Inspected separately by the test."},
    }
    files = {"story.json": encoded(story), "validation_report.json": encoded(report)}
    if stage >= 2:
        plan = {
            "schema_version": "4.1.3", "image_mode": "ZONE", "reference_mode": "IMAGE_REFERENCE",
            "targets": {orientation: {"size_policy": "MODEL_DEFAULT", "preferred_aspect_ratio": ratio,
                                      "width": None, "height": None}
                        for orientation, ratio in (("landscape", "16:9"), ("portrait", "9:16"))},
            "characters": [{"character_id": row["character_id"], "planned_reference_path": f"characters/{row['character_id']}.png",
                            "reference_path": f"characters/{row['character_id']}.png", "reference_status": "READY",
                            "description_lock": row["appearance"]} for row in story["characters"]],
            "assets": [{"basename": f"{stem}.png", "role": stem.upper(),
                        "source_script_ids": [story["script"][max(0, min(i - 1, 7))]["id"]],
                        "character_ids": ["c001", "c002", "c003"], "brief": f"Cảnh {stem}",
                        "landscape_prompt": f"Ảnh ngang {stem}", "portrait_prompt": f"Ảnh dọc {stem}"}
                       for i, stem in enumerate(STEMS)],
        }
        files.update({"visual_plan.json": encoded(plan), "visual_bible.txt": b"Synthetic consistent visual style."})
        for row in story["characters"]:
            files[f"characters/{row['character_id']}.png"] = png((32, 32))
        for stem in STEMS:
            files[f"landscape/{stem}.png"] = png((48, 32))
            if stage >= 3:
                files[f"portrait/{stem}.png"] = png((32, 48))
    if stage == 4:
        files["video_prompts.json"] = encoded({
            "schema_version": "4.1.3", "source_mode": "STAGE3_PACKAGE", "target_model": None,
            "coverage": "FULL_STORY", "timing_basis": "ESTIMATED",
            "timing_config": {"method_id": "WHITESPACE_RATE_V1", "rate_per_minute": 200, "evidence_locator": None},
            "clips": [{"clip_id": f"clip_{i:04d}", "source_spans": [{"script_id": row["id"],
                        "start_char": 0, "end_char": len(row["text"])}], "estimated_seconds": 3.0,
                       "aspect_ratio": "16:9", "reference_paths": ["landscape/cover.png"],
                       "prompt": "Các bạn mở cửa", "narration": row["text"], "audio_note": "", "transition": "CUT"}
                      for i, row in enumerate(story["script"], 1)],
            "limitations": [],
        })
    return files


def write_legacy_archives(directory: Path) -> Path:
    """Create all four stages independently of the production package builder."""
    directory.mkdir(parents=True, exist_ok=True)
    checksums = []
    parent_digest = None
    for stage, filename in enumerate(ARCHIVES, 1):
        files = legacy_files(stage)
        rows = [{"path": name, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                 "origin_stage": 1 if name == "story.json" else stage if name == "validation_report.json"
                 else 4 if name == "video_prompts.json" else 3 if name.startswith("portrait/") else 2}
                for name, raw in sorted(files.items())]
        manifest = {"schema_version": "4.1.3", "prompt_version": "4.1.6", "stage": stage,
                    "status": "COMPLETE", "parent_package_sha256": parent_digest, "files": rows}
        with zipfile.ZipFile(directory / filename, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in sorted({**files, "manifest.json": encoded(manifest)}.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, raw)
        checksums.append(f"{hashlib.sha256((directory / filename).read_bytes()).hexdigest()}  {filename}\n")
        parent_digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (directory / "SHA256SUMS").write_text("".join(checksums), encoding="utf-8")
    return directory
