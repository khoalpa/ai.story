"""Strict Audio-module support for ChatGPT Audio Story packages v4.1.6.

The package prompt version is 4.1.6 while every public JSON document uses
schema_version 4.1.3.  This module intentionally contains no legacy adapter.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from studio.artifact_validation import strict_json_bytes
from studio.workflow_package import inspect_directory, inspect_members, read_archive

SCHEMA_VERSION = "4.1.3"
PROMPT_VERSION = "4.1.6"
ROOT_FIELDS = {"schema_version", "meta", "characters", "outline", "script"}
META_FIELDS = {
    "title", "series", "episode", "author", "channel", "profile", "age_band",
    "language", "genre", "tone", "target_minutes", "estimated_minutes",
    "timing_method", "tags",
}
CHARACTER_FIELDS = {
    "character_id", "name", "age", "role", "appearance", "personality", "voice_note",
}
OUTLINE_FIELDS = {"scene_id", "summary", "change", "setup_or_payoff"}
SCRIPT_FIELDS = {
    "id", "zone", "scene_id", "speaker", "text", "emotion", "speed", "pause_ms", "ambience",
}
ZONES = (
    "GREETING", "OPENING", "INTRODUCTION", "DEVELOPMENT", "CLIMAX", "FALLING", "ENDING", "FAREWELL",
)
ZONE_LABELS = {
    "GREETING": "LỜI CHÀO", "OPENING": "MỞ TRUYỆN", "INTRODUCTION": "GIỚI THIỆU",
    "DEVELOPMENT": "TRIỂN KHAI", "CLIMAX": "CAO TRÀO", "FALLING": "HẠ MÀN",
    "ENDING": "KẾT TRUYỆN", "FAREWELL": "TẠM BIỆT",
}
PROFILES = {"YOUTH_SAFE", "ADULT_STANDARD", "SERIAL_DETECTIVE"}
YOUTH_AGES = {"3-6", "7-10", "11-14", "15-18"}
ID_RE = re.compile(r"[a-z][0-9]+")


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_positive(value: object) -> bool:
    return (type(value) is int or type(value) is float) and math.isfinite(value) and value > 0


def parse_story_text(text: str) -> dict[str, Any]:
    try:
        value = strict_json_bytes(text.encode("utf-8"))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"story.json không phải JSON UTF-8 nghiêm ngặt: {exc}") from exc
    story = dict(value)
    errors = validate_story(story)
    if errors:
        raise ValueError("story.json không đúng gói v4.1.6:\n- " + "\n- ".join(errors))
    return story


def validate_story(story: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(story, Mapping):
        return ["Root phải là object."]
    if set(story) != ROOT_FIELDS:
        errors.append(f"Root phải có đúng closed schema {sorted(ROOT_FIELDS)}.")
    if story.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version phải là {SCHEMA_VERSION}; gói cũ không được hỗ trợ.")

    meta = story.get("meta")
    if not isinstance(meta, Mapping) or set(meta) != META_FIELDS:
        errors.append("meta không đúng closed schema v4.1.3.")
        meta = {}
    for key in ("title", "author", "channel", "language", "genre", "tone", "timing_method"):
        if not _nonempty(meta.get(key)):
            errors.append(f"meta.{key} phải là string không rỗng.")
    if meta.get("series") is not None and not _nonempty(meta.get("series")):
        errors.append("meta.series phải là string không rỗng hoặc null.")
    if type(meta.get("episode")) is not int or meta.get("episode", 0) < 1:
        errors.append("meta.episode phải là integer >= 1.")
    profile = meta.get("profile")
    if not isinstance(profile, str) or profile not in PROFILES:
        errors.append("meta.profile không hợp lệ.")
    expected_ages = YOUTH_AGES if profile == "YOUTH_SAFE" else {"18+"}
    if not isinstance(meta.get("age_band"), str) or meta.get("age_band") not in expected_ages:
        errors.append("meta.age_band không khớp profile.")
    if not _finite_positive(meta.get("target_minutes")):
        errors.append("meta.target_minutes phải là number > 0.")
    if meta.get("estimated_minutes") is not None and not _finite_positive(meta.get("estimated_minutes")):
        errors.append("meta.estimated_minutes phải là number > 0 hoặc null.")
    tags = meta.get("tags")
    if not isinstance(tags, list) or not tags or not all(_nonempty(tag) for tag in tags):
        errors.append("meta.tags phải là array string không rỗng.")
    elif len({tag.casefold() for tag in tags}) != len(tags):
        errors.append("meta.tags không được trùng.")

    characters = story.get("characters")
    character_ids: list[str] = []
    if not isinstance(characters, list) or not characters:
        errors.append("characters phải là array không rỗng.")
    else:
        for index, row in enumerate(characters, 1):
            if not isinstance(row, Mapping) or set(row) != CHARACTER_FIELDS:
                errors.append(f"characters[{index}] không đúng closed schema.")
                continue
            cid = row.get("character_id")
            if not isinstance(cid, str) or re.fullmatch(r"c[0-9]{3,}", cid) is None:
                errors.append(f"characters[{index}].character_id không hợp lệ.")
            else:
                character_ids.append(cid)
            for key in ("name", "role", "appearance", "personality", "voice_note"):
                if not _nonempty(row.get(key)):
                    errors.append(f"characters[{index}].{key} phải là string không rỗng.")
            if row.get("age") is not None and (type(row.get("age")) is not int or row["age"] < 0):
                errors.append(f"characters[{index}].age phải là integer >= 0 hoặc null.")
        if len(character_ids) != len(set(character_ids)):
            errors.append("character_id phải duy nhất.")

    outline = story.get("outline")
    scene_ids: list[str] = []
    if not isinstance(outline, list) or not outline:
        errors.append("outline phải là array không rỗng.")
    else:
        for index, row in enumerate(outline, 1):
            if not isinstance(row, Mapping) or set(row) != OUTLINE_FIELDS:
                errors.append(f"outline[{index}] không đúng closed schema.")
                continue
            scene_id = row.get("scene_id")
            expected = f"sc{index:03d}"
            if scene_id != expected:
                errors.append(f"outline[{index}].scene_id phải là {expected}.")
            elif isinstance(scene_id, str):
                scene_ids.append(scene_id)
            for key in ("summary", "change"):
                if not _nonempty(row.get(key)):
                    errors.append(f"outline[{index}].{key} phải là string không rỗng.")
            if row.get("setup_or_payoff") is not None and not isinstance(row.get("setup_or_payoff"), str):
                errors.append(f"outline[{index}].setup_or_payoff phải là string hoặc null.")

    script = story.get("script")
    used_scenes: list[str] = []
    last_zone = -1
    last_scene = -1
    closed_scenes: set[str] = set()
    active_scene: str | None = None
    if not isinstance(script, list) or not script:
        errors.append("script phải là array không rỗng.")
    else:
        for index, row in enumerate(script, 1):
            if not isinstance(row, Mapping) or set(row) != SCRIPT_FIELDS:
                errors.append(f"script[{index}] không đúng closed schema.")
                continue
            if row.get("id") != f"s{index:04d}":
                errors.append(f"script[{index}].id phải là s{index:04d}.")
            zone = row.get("zone")
            if zone not in ZONES:
                errors.append(f"script[{index}].zone không hợp lệ.")
            else:
                pos = ZONES.index(zone)
                if pos < last_zone:
                    errors.append(f"script[{index}].zone đi lùi.")
                last_zone = max(last_zone, pos)
            scene_id = row.get("scene_id")
            if scene_id not in scene_ids:
                errors.append(f"script[{index}].scene_id không tham chiếu outline.")
            else:
                pos = scene_ids.index(scene_id)
                if pos < last_scene:
                    errors.append(f"script[{index}].scene_id đi lùi.")
                last_scene = max(last_scene, pos)
                if scene_id != active_scene:
                    if scene_id in closed_scenes:
                        errors.append(f"script[{index}] quay lại scene đã đóng.")
                    if active_scene is not None:
                        closed_scenes.add(active_scene)
                    active_scene = scene_id
                    used_scenes.append(scene_id)
            if row.get("speaker") != "narrator" and row.get("speaker") not in character_ids:
                errors.append(f"script[{index}].speaker không hợp lệ.")
            for key in ("text", "emotion"):
                if not _nonempty(row.get(key)):
                    errors.append(f"script[{index}].{key} phải là string không rỗng.")
            if not _finite_positive(row.get("speed")):
                errors.append(f"script[{index}].speed phải là number > 0.")
            if type(row.get("pause_ms")) is not int or row.get("pause_ms", -1) < 0:
                errors.append(f"script[{index}].pause_ms phải là integer >= 0.")
            if row.get("ambience") is not None and not isinstance(row.get("ambience"), str):
                errors.append(f"script[{index}].ambience phải là string hoặc null.")
        if scene_ids and used_scenes != scene_ids:
            errors.append("Mỗi scene phải được dùng đúng thứ tự và liên tiếp trong script.")
        present_zones = [r.get("zone") for r in script if isinstance(r, Mapping)]
        missing_zones = [zone for zone in ZONES if zone not in present_zones]
        if missing_zones:
            errors.append(f"script thiếu zone bắt buộc: {missing_zones}.")
    return errors


def _voice_for(speaker: object, characters: Mapping[str, Mapping[str, Any]]) -> str:
    if speaker == "narrator":
        return "NARRATOR"
    note = str(characters.get(str(speaker), {}).get("voice_note") or "").casefold()
    if any(token in note for token in ("giọng nam", "bé trai", "đàn ông", "male voice")):
        return "MALE"
    if any(token in note for token in ("giọng nữ", "bé gái", "phụ nữ", "female voice")):
        return "FEMALE"
    return "NARRATOR"


def render_plain_script(story: Mapping[str, Any]) -> str:
    errors = validate_story(story)
    if errors:
        raise ValueError("story.json không đúng gói v4.1.6:\n- " + "\n- ".join(errors))
    meta = story["meta"]
    lines = [
        "# FORMAT: AUDIO_STORY_PLAIN v1.1.0", "# SOURCE_PROMPT: 4.1.6", "# SOURCE_SCHEMA: 4.1.3",
        f"# TITLE: {meta['title']}", f"# SERIES: {meta['series']}" if meta["series"] else "# SERIES: standalone",
        f"# EPISODE: {meta['episode']}", f"# AUTHOR: {meta['author']}", f"# CHANNEL: {meta['channel']}",
        f"# TARGET: {meta['profile']} / {meta['age_band']}", f"# LENGTH: {meta['target_minutes']} phút", "", "SCRIPT:", "",
    ]
    characters = {row["character_id"]: row for row in story["characters"]}
    previous_zone: str | None = None
    for row in story["script"]:
        zone = row["zone"]
        if zone != previous_zone:
            if previous_zone is not None:
                lines.append("")
            lines.append(f"// {ZONE_LABELS[zone]}")
            previous_zone = zone
        voice = _voice_for(row["speaker"], characters)
        language = str(meta["language"]).upper()
        speed_delta = (float(row["speed"]) - 1.0) * 100.0
        tags = [voice, f"RATE={speed_delta:+g}%", language]
        ambience = row.get("ambience")
        if isinstance(ambience, str) and ambience.strip():
            tags.append(f"SFX={ambience.strip()}")
        lines.append("".join(f"[{tag}]" for tag in tags) + " " + row["text"].strip())
        if row["pause_ms"]:
            lines.append(f"[PAUSE={row['pause_ms']}ms]")
    return "\n".join(lines).rstrip() + "\n"


def raw_script(story: Mapping[str, Any]) -> str:
    errors = validate_story(story)
    if errors:
        raise ValueError("story.json không đúng gói v4.1.6:\n- " + "\n- ".join(errors))
    return "\n".join(row["text"].strip() for row in story["script"])


def load_package_bytes(raw: bytes) -> tuple[str, dict[str, Any]]:
    members = read_archive(raw)
    inspection = inspect_members(members, archive=True)
    if inspection.get("compatibility") != "NATIVE_CURRENT" or inspection.get("status") != "PASS":
        details = [row.get("detail", "") for row in inspection.get("checks", []) if row.get("status") != "PASS"]
        raise ValueError("ZIP không phải gói v4.1.6 hợp lệ: " + "; ".join(filter(None, details)))
    story_raw = members.get("story.json")
    if story_raw is None:
        raise ValueError("ZIP thiếu story.json.")
    story = dict(strict_json_bytes(story_raw))
    errors = validate_story(story)
    if errors:
        raise ValueError("story.json trong ZIP không hợp lệ:\n- " + "\n- ".join(errors))
    return story_raw.decode("utf-8"), inspection


def load_project_directory(root: Path) -> tuple[str, dict[str, Any]]:
    inspection = inspect_directory(root)
    if inspection.get("compatibility") != "NATIVE_CURRENT" or inspection.get("status") != "PASS":
        details = [row.get("detail", "") for row in inspection.get("checks", []) if row.get("status") != "PASS"]
        raise ValueError("Thư mục không phải gói v4.1.6 hợp lệ: " + "; ".join(filter(None, details)))
    path = root / "story.json"
    text = path.read_text(encoding="utf-8")
    parse_story_text(text)
    return text, inspection


__all__ = [
    "PROMPT_VERSION", "SCHEMA_VERSION", "load_package_bytes", "load_project_directory",
    "parse_story_text", "raw_script", "render_plain_script", "validate_story",
]
