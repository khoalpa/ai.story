"""Re-segment a Stage 4 plan on complete script-item sentence boundaries.

Each story script item is treated as one authored sentence/utterance.  The
result keeps its usable spoken span below eight seconds while selecting the
smallest canonical 4/6/8-second video container that can hold it.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from studio.video_prompt_validation import (
    VOICE_CLIP_FIELDS,
    _source_digest,
    canonical_output_digest,
    normalize_video_prompt_plan,
    validate_video_prompt_plan,
)
from studio.video_voice import (
    build_voice_plan,
    default_voice_strategy,
    native_audio_prompt,
)
from studio.workflow_package import package_digest

SPEED = {"SLOW": 0.85, "NORMAL": 1.0, "FAST": 1.15}
PAUSE = {".": 0.35, "?": 0.45, "!": 0.40, "…": 0.60}
MAX_USABLE_SECONDS = 7.950


def _round(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sentence_durations(script: list[dict[str, Any]], total_seconds: float) -> list[float]:
    raw: list[float] = []
    for item in script:
        text = str(item["text"]).strip()
        words = len(text.split())
        active = 60 * words / (200 * SPEED[str(item["speed"])])
        raw.append(active + PAUSE.get(text[-1:], 0.20))
    scaled = [value * total_seconds / sum(raw) for value in raw]

    # A tiny overflow can occur for a long SLOW sentence.  Move it to shorter
    # sentences instead of cutting text or exceeding the eight-second clip.
    overflow = sum(max(0.0, value - MAX_USABLE_SECONDS) for value in scaled)
    scaled = [min(value, MAX_USABLE_SECONDS) for value in scaled]
    recipients = [index for index, value in enumerate(scaled) if value < 6.0]
    share = overflow / len(recipients) if recipients else 0.0
    for index in recipients:
        scaled[index] += share

    rounded = [_round(value) for value in scaled]
    rounded[-1] = _round(rounded[-1] + total_seconds - sum(rounded))
    if any(value >= 8 for value in rounded):
        raise ValueError("Không thể giữ mọi sentence span dưới 8 giây")
    return rounded


def _container_duration(usable: float) -> int:
    for duration in (4, 6, 8):
        if usable <= duration:
            return duration
    raise ValueError(f"Sentence span vượt container 8 giây: {usable}")


def _template_for_item(clips: list[dict[str, Any]], item_index: int) -> dict[str, Any]:
    for clip in clips:
        source = clip.get("source_script", {})
        if source.get("start_item_index", 10**9) <= item_index <= source.get("end_item_index", -1):
            return clip
    raise ValueError(f"Không tìm thấy clip template cho script item {item_index}")


def resegment(root: Path) -> dict[str, Any]:
    story_path = root / "story.json"
    plan_path = root / "video_prompts.json"
    manifest_path = root / "workflow_manifest.json"
    story = json.loads(story_path.read_text(encoding="utf-8"))
    original = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    script = story["script"]
    total_seconds = float(original["project"]["total_story_duration_seconds"])
    durations = _sentence_durations(script, total_seconds)
    boundaries = [0.0]
    for duration in durations:
        boundaries.append(_round(boundaries[-1] + duration))
    boundaries[-1] = _round(total_seconds)

    strategy = default_voice_strategy()
    plan: dict[str, Any] = {}
    for key, value in original.items():
        plan[key] = copy.deepcopy(value)
        if key == "project":
            plan["voice_strategy"] = strategy
    plan["generator_target"]["capability_profile"]["audio_mode"] = "NATIVE_DIALOGUE"

    new_clips: list[dict[str, Any]] = []
    previous_by_scene: dict[str, dict[str, Any]] = {}
    for item_index, item in enumerate(script):
        template = _template_for_item(original["clips"], item_index)
        clip = copy.deepcopy(template)
        sequence = item_index + 1
        clip["clip_id"] = f"clip_{sequence:04d}"
        clip["sequence_index"] = sequence
        clip["zone"] = item["zone"]
        words = len(str(item["text"]).split())
        source = {
            "start_item_index": item_index,
            "start_word_offset": 0,
            "end_item_index": item_index,
            "end_word_offset": words,
            "start_time_seconds": boundaries[item_index],
            "end_time_seconds": boundaries[item_index + 1],
            "pause_only": False,
        }
        source["source_text_digest_sha256"] = _source_digest(script, source)
        clip["source_script"] = source
        usable = _round(boundaries[item_index + 1] - boundaries[item_index])
        clip["duration_seconds"] = _container_duration(usable)
        clip["usable_span_seconds"] = usable
        sentence = str(item["text"]).strip()
        clip["primary_action"] = f"Visualize exactly this complete source sentence: {sentence}"
        clip["visual_delta"] = f"One sentence-bound visual beat for story item {item_index}."
        clip["terminal_handoff"] = "End after the complete sentence; hold a stable continuity frame."
        base_prompt = str(template["prompt"])
        clip["prompt"] = (
            f"{base_prompt}\nExact complete source sentence for this clip only: {sentence} "
            f"Do not show content from adjacent sentences."
        )
        voice_plan = build_voice_plan(script, source)
        ambience = str(template["audio_prompt"])
        clip["voice_plan"] = voice_plan
        clip["audio_prompt"] = native_audio_prompt(voice_plan, strategy, ambience)

        scene_id = str(clip["derived_scene_id"])
        previous = previous_by_scene.get(scene_id)
        refs = clip["reference_inputs"]
        refs["previous_clip_id"] = previous["clip_id"] if previous else None
        refs["previous_last_frame_required"] = previous is not None
        refs["previous_output_last_frame"] = previous is not None
        refs["previous_output_video_required"] = False
        if previous is not None:
            clip["continuity_in"] = copy.deepcopy(previous["continuity_out"])
        clip = {key: clip.get(key) for key in VOICE_CLIP_FIELDS}
        previous_by_scene[scene_id] = clip
        new_clips.append(clip)

    plan["clips"] = new_clips
    project = plan["project"]
    project["clip_count"] = len(new_clips)
    project["planned_covered_duration_seconds"] = _round(total_seconds)
    project["planned_video_duration_seconds"] = sum(clip["duration_seconds"] for clip in new_clips)
    plan["validation"]["output_digest_sha256"] = canonical_output_digest(plan)
    plan = normalize_video_prompt_plan(plan, story)

    result = validate_video_prompt_plan(plan, root=root)
    if result["errors"]:
        raise ValueError("; ".join(result["errors"][:20]))

    backup = root.parent / "tmp" / "sentence_boundary_voice_backup"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plan_path, backup / "video_prompts.json")
    shutil.copy2(manifest_path, backup / "workflow_manifest.json")
    plan_raw = _encoded(plan)
    row = next(item for item in manifest["files"] if item["path"] == "video_prompts.json")
    row["sha256"] = hashlib.sha256(plan_raw).hexdigest()
    row["size_bytes"] = len(plan_raw)
    manifest["package_digest_sha256"] = package_digest(manifest["files"])
    plan_path.write_bytes(plan_raw)
    manifest_path.write_bytes(_encoded(manifest))
    return {"clip_count": len(new_clips), "max_usable_seconds": max(durations),
            "planned_video_duration_seconds": project["planned_video_duration_seconds"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path(r"D:\project\ai.story\output"))
    args = parser.parse_args()
    print(json.dumps(resegment(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
