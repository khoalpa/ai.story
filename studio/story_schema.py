"""Closed-schema validation shared by Story Studio and package inspectors."""
from __future__ import annotations

import math
import re
from typing import Any, Mapping

ROOT_FIELDS = {"schema_version", "meta", "characters", "outline", "script"}
META_FIELDS = {"title", "series", "episode", "author", "channel", "profile", "age_band", "language", "genre", "tone", "target_minutes", "estimated_minutes", "timing_method", "tags"}
CHARACTER_FIELDS = {"character_id", "name", "age", "role", "appearance", "personality", "voice_note"}
OUTLINE_FIELDS = {"scene_id", "summary", "change", "setup_or_payoff"}
SCRIPT_FIELDS = {"id", "zone", "scene_id", "speaker", "text", "emotion", "speed", "pause_ms", "ambience"}
ZONES = ("GREETING", "OPENING", "INTRODUCTION", "DEVELOPMENT", "CLIMAX", "FALLING", "ENDING", "FAREWELL")
PROFILES = {"YOUTH_SAFE", "ADULT_STANDARD", "SERIAL_DETECTIVE"}


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive(value: object) -> bool:
    return (type(value) is int or type(value) is float) and math.isfinite(value) and value > 0


def validate_story_document(story: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(story, Mapping):
        return ["story.json root phải là object"]
    if set(story) != ROOT_FIELDS:
        errors.append("story.json root không đúng closed schema")
    if story.get("schema_version") != "4.1.3":
        errors.append("story.schema_version phải là 4.1.3")
    meta = story.get("meta")
    if not isinstance(meta, Mapping) or set(meta) != META_FIELDS:
        errors.append("story.meta không đúng closed schema")
        meta = {}
    for key in ("title", "author", "channel", "language", "genre", "tone", "timing_method"):
        if not _text(meta.get(key)):
            errors.append(f"meta.{key} phải là string không rỗng")
    if meta.get("series") is not None and not _text(meta.get("series")):
        errors.append("meta.series phải là string không rỗng hoặc null")
    if type(meta.get("episode")) is not int or meta.get("episode", 0) < 1:
        errors.append("meta.episode phải là integer >= 1")
    profile = meta.get("profile")
    if profile not in PROFILES:
        errors.append("meta.profile không hợp lệ")
    if profile == "SERIAL_DETECTIVE" and not _text(meta.get("series")):
        errors.append("SERIAL_DETECTIVE yêu cầu meta.series")
    ages = {"3-6", "7-10", "11-14", "15-18"} if profile == "YOUTH_SAFE" else {"18+"}
    if meta.get("age_band") not in ages:
        errors.append("meta.age_band không khớp profile")
    if not _positive(meta.get("target_minutes")):
        errors.append("meta.target_minutes phải là number > 0")
    if meta.get("estimated_minutes") is not None and not _positive(meta.get("estimated_minutes")):
        errors.append("meta.estimated_minutes phải là number > 0 hoặc null")
    tags = meta.get("tags")
    if not isinstance(tags, list) or not tags or not all(_text(tag) for tag in tags):
        errors.append("meta.tags phải là array string không rỗng")
    elif len({tag.casefold() for tag in tags}) != len(tags):
        errors.append("meta.tags không được trùng")

    characters = story.get("characters")
    character_ids: list[str] = []
    if not isinstance(characters, list) or not characters:
        errors.append("characters phải là array không rỗng")
    else:
        for index, row in enumerate(characters, 1):
            if not isinstance(row, Mapping) or set(row) != CHARACTER_FIELDS:
                errors.append(f"characters[{index}] không đúng closed schema")
                continue
            cid = row.get("character_id")
            if not isinstance(cid, str) or re.fullmatch(r"c[0-9]{3,}", cid) is None:
                errors.append(f"characters[{index}].character_id không hợp lệ")
            else:
                character_ids.append(cid)
            for key in ("name", "role", "appearance", "personality", "voice_note"):
                if not _text(row.get(key)):
                    errors.append(f"characters[{index}].{key} phải là string không rỗng")
            if row.get("age") is not None and (type(row.get("age")) is not int or row["age"] < 0):
                errors.append(f"characters[{index}].age không hợp lệ")
    if len(character_ids) != len(set(character_ids)):
        errors.append("character_id phải duy nhất")

    outline = story.get("outline")
    scene_ids: list[str] = []
    if not isinstance(outline, list) or not outline:
        errors.append("outline phải là array không rỗng")
    else:
        for index, row in enumerate(outline, 1):
            if not isinstance(row, Mapping) or set(row) != OUTLINE_FIELDS:
                errors.append(f"outline[{index}] không đúng closed schema")
                continue
            expected = f"sc{index:03d}"
            if row.get("scene_id") != expected:
                errors.append(f"outline[{index}].scene_id phải là {expected}")
            else:
                scene_ids.append(expected)
            if not _text(row.get("summary")) or not _text(row.get("change")):
                errors.append(f"outline[{index}] thiếu summary/change")
            if row.get("setup_or_payoff") is not None and not isinstance(row.get("setup_or_payoff"), str):
                errors.append(f"outline[{index}].setup_or_payoff không hợp lệ")

    script = story.get("script")
    used_scenes: list[str] = []
    last_zone = last_scene = -1
    closed_scenes: set[str] = set()
    active_scene: str | None = None
    if not isinstance(script, list) or not script:
        errors.append("script phải là array không rỗng")
    else:
        for index, row in enumerate(script, 1):
            if not isinstance(row, Mapping) or set(row) != SCRIPT_FIELDS:
                errors.append(f"script[{index}] không đúng closed schema")
                continue
            if row.get("id") != f"s{index:04d}":
                errors.append(f"script[{index}].id không liên tục")
            zone = row.get("zone")
            if zone not in ZONES:
                errors.append(f"script[{index}].zone không hợp lệ")
            else:
                position = ZONES.index(zone)
                if position < last_zone:
                    errors.append(f"script[{index}].zone đi lùi")
                last_zone = max(last_zone, position)
            scene_id = row.get("scene_id")
            if scene_id not in scene_ids:
                errors.append(f"script[{index}].scene_id không tồn tại")
            else:
                position = scene_ids.index(scene_id)
                if position < last_scene:
                    errors.append(f"script[{index}].scene_id đi lùi")
                last_scene = max(last_scene, position)
                if scene_id != active_scene:
                    if scene_id in closed_scenes:
                        errors.append(f"script[{index}] quay lại scene đã đóng")
                    if active_scene is not None:
                        closed_scenes.add(active_scene)
                    active_scene = scene_id
                    used_scenes.append(scene_id)
            if row.get("speaker") != "narrator" and row.get("speaker") not in character_ids:
                errors.append(f"script[{index}].speaker không hợp lệ")
            if not _text(row.get("text")) or not _text(row.get("emotion")):
                errors.append(f"script[{index}] thiếu text/emotion")
            if not _positive(row.get("speed")):
                errors.append(f"script[{index}].speed không hợp lệ")
            if type(row.get("pause_ms")) is not int or row.get("pause_ms", -1) < 0:
                errors.append(f"script[{index}].pause_ms không hợp lệ")
            if row.get("ambience") is not None and not isinstance(row.get("ambience"), str):
                errors.append(f"script[{index}].ambience không hợp lệ")
        if scene_ids and used_scenes != scene_ids:
            errors.append("Mỗi outline scene phải được dùng đúng thứ tự và liên tiếp")
        missing = [zone for zone in ZONES if zone not in [row.get("zone") for row in script if isinstance(row, Mapping)]]
        if missing:
            errors.append("script thiếu zone bắt buộc: " + ", ".join(missing))
    return errors


__all__ = ["validate_story_document"]
