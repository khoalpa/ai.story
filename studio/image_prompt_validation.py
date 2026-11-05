"""Closed-schema validation for v5 image_prompts.json."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping

from studio.artifact_validation import strict_json_bytes

ROOT_FIELDS_V1 = {
    "image_prompt_version", "prompt_version", "source_story", "image_mode",
    "style_lock", "character_locks", "assets", "limitations",
}
ROOT_FIELDS = ROOT_FIELDS_V1 | {"prompt_encoding", "characters_prompt"}
SOURCE_FIELDS = {"schema_version", "sha256"}
PROMPT_ENCODING_FIELDS = {
    "standard", "tokenizer_id", "max_tokens", "count_scope", "overflow_policy",
}
CHARACTER_FIELDS = {"character_id", "description_lock", "planned_reference_path"}
ASSET_FIELDS = {
    "asset_id", "basename", "role", "source_script_ids", "character_ids", "brief",
    "landscape_prompt", "portrait_prompt", "must_show", "must_avoid",
}
SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
DIGEST = re.compile(r"[0-9a-f]{64}")
ZONE_BASENAMES = ("cover.png", "greeting.png", "opening.png", "introduction.png", "development.png", "climax.png", "falling.png", "ending.png", "farewell.png", "outro.png")


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_basename(value: object) -> bool:
    return (isinstance(value, str) and value == value.strip() and "/" not in value
            and "\\" not in value and ":" not in value and value not in {"", ".", ".."})


def _unique_strings(value: object, *, allow_empty: bool = True) -> bool:
    return (isinstance(value, list) and (allow_empty or bool(value))
            and all(_nonempty(item) for item in value) and len(value) == len(set(value)))


def validate_image_prompt_plan(
    plan: Mapping[str, Any], story: Mapping[str, Any], story_raw: bytes,
    *, expected_prompt_version: str | None = None,
) -> list[str]:
    errors: list[str] = []
    prompt_version = plan.get("prompt_version")
    is_t5_contract = prompt_version in {"5.2.0", "5.2.2"}
    expected_root = ROOT_FIELDS if is_t5_contract else ROOT_FIELDS_V1
    if set(plan) != expected_root:
        errors.append("image_prompts root không đúng closed schema")
    expected_image_version = "1.1" if is_t5_contract else "1.0"
    if (plan.get("image_prompt_version") != expected_image_version
            or prompt_version not in {"5.0.0", "5.1.0", "5.2.0", "5.2.2"}):
        errors.append("image_prompt_version/prompt_version không hợp lệ")
    if expected_prompt_version is not None and plan.get("prompt_version") != expected_prompt_version:
        errors.append(f"prompt_version phải khớp package: {expected_prompt_version}")
    source = plan.get("source_story")
    if not isinstance(source, Mapping) or set(source) != SOURCE_FIELDS:
        errors.append("source_story không đúng closed schema")
    elif (source.get("schema_version") != "4.1.3" or not isinstance(source.get("sha256"), str)
          or DIGEST.fullmatch(source["sha256"]) is None
          or source["sha256"] != hashlib.sha256(story_raw).hexdigest()):
        errors.append("source_story không khớp exact bytes story.json")
    if plan.get("image_mode") not in {"ZONE", "SCENE"} or not _nonempty(plan.get("style_lock")):
        errors.append("image_mode/style_lock không hợp lệ")
    if is_t5_contract:
        encoding = plan.get("prompt_encoding")
        if (not isinstance(encoding, Mapping) or set(encoding) != PROMPT_ENCODING_FIELDS
                or encoding.get("standard") != "T5-512"
                or not _nonempty(encoding.get("tokenizer_id"))
                or encoding.get("max_tokens") != 512
                or encoding.get("count_scope") != "RESOLVED_IMAGE_PROMPT"
                or encoding.get("overflow_policy") != "REWRITE"):
            errors.append("prompt_encoding phải khai báo đúng tiêu chuẩn T5-512")
        if not _nonempty(plan.get("characters_prompt")):
            errors.append("characters_prompt phải là string khác rỗng")
    if not _unique_strings(plan.get("limitations")):
        errors.append("limitations phải là array string duy nhất")

    story_characters = story.get("characters")
    character_ids = {
        row.get("character_id") for row in story_characters
        if isinstance(row, Mapping) and isinstance(row.get("character_id"), str)
    } if isinstance(story_characters, list) else set()
    locks = plan.get("character_locks")
    seen_locks: set[str] = set()
    planned_by_character: dict[str, str | None] = {}
    if not isinstance(locks, list):
        errors.append("character_locks phải là array")
    else:
        for index, row in enumerate(locks):
            if not isinstance(row, Mapping) or set(row) != CHARACTER_FIELDS:
                errors.append(f"character_locks[{index}] không đúng closed schema")
                continue
            character_id = row.get("character_id")
            planned = row.get("planned_reference_path")
            if (character_id not in character_ids or character_id in seen_locks
                    or not _nonempty(row.get("description_lock"))
                    or planned not in {None, f"characters/{character_id}.png"}):
                errors.append(f"character_locks[{index}] không hợp lệ")
            if isinstance(character_id, str):
                seen_locks.add(character_id)
                planned_by_character[character_id] = planned if isinstance(planned, str) else None

    script = story.get("script")
    script_ids = {
        row.get("id") for row in script
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    } if isinstance(script, list) else set()
    assets = plan.get("assets")
    names: list[str] = []
    asset_ids: list[str] = []
    visible_character_ids: set[str] = set()
    if not isinstance(assets, list) or not assets:
        errors.append("assets phải là array khác rỗng")
    else:
        for index, row in enumerate(assets):
            if not isinstance(row, Mapping) or set(row) != ASSET_FIELDS:
                errors.append(f"assets[{index}] không đúng closed schema")
                continue
            asset_id, basename = row.get("asset_id"), row.get("basename")
            valid = (isinstance(asset_id, str) and SAFE_ID.fullmatch(asset_id) is not None
                     and isinstance(basename, str) and _safe_basename(basename)
                     and basename.endswith(".png") and _nonempty(row.get("role"))
                     and _nonempty(row.get("brief")) and _nonempty(row.get("landscape_prompt"))
                     and _nonempty(row.get("portrait_prompt"))
                     and _unique_strings(row.get("source_script_ids"), allow_empty=False)
                     and set(row.get("source_script_ids", [])) <= script_ids
                     and _unique_strings(row.get("character_ids"))
                     and set(row.get("character_ids", [])) <= character_ids
                     and _unique_strings(row.get("must_show"))
                     and _unique_strings(row.get("must_avoid")))
            if not valid:
                errors.append(f"assets[{index}] không hợp lệ hoặc tham chiếu story sai")
            if isinstance(asset_id, str):
                asset_ids.append(asset_id)
            if isinstance(basename, str):
                names.append(basename)
            if isinstance(row.get("character_ids"), list):
                visible_character_ids.update(
                    value for value in row["character_ids"] if isinstance(value, str)
                )
    if len(asset_ids) != len(set(asset_ids)) or len(names) != len(set(name.casefold() for name in names)):
        errors.append("asset_id/basename phải duy nhất")
    if not visible_character_ids <= seen_locks:
        errors.append("Mọi nhân vật xuất hiện trong assets phải có character_lock")
    reference_modes = {
        planned_by_character.get(character_id) is not None
        for character_id in visible_character_ids if character_id in planned_by_character
    }
    if len(reference_modes) > 1:
        errors.append("Không hỗ trợ trộn IMAGE_REFERENCE và DESCRIPTION_ONLY trong cùng plan")
    if plan.get("image_mode") == "ZONE" and tuple(names) != ZONE_BASENAMES:
        errors.append("Bộ basename ZONE không đúng canonical")
    if plan.get("image_mode") == "SCENE":
        middle = names[2:-2]
        if (names[:2] != ["cover.png", "greeting.png"] or names[-2:] != ["farewell.png", "outro.png"]
                or middle != [f"scene_{index:04d}.png" for index in range(1, len(middle) + 1)]):
            errors.append("Bộ basename SCENE không đúng canonical")
    return errors


def validate_image_prompt_bytes(
    raw: bytes, story_raw: bytes, *, expected_prompt_version: str | None = None,
) -> list[str]:
    try:
        plan = strict_json_bytes(raw)
        story = strict_json_bytes(story_raw)
    except (UnicodeError, ValueError) as exc:
        return [f"JSON không hợp lệ: {exc}"]
    if not isinstance(plan, Mapping) or not isinstance(story, Mapping):
        return ["image_prompts/story root phải là object"]
    return validate_image_prompt_plan(
        plan, story, story_raw, expected_prompt_version=expected_prompt_version,
    )


def render_image_prompt_plan(plan: Mapping[str, Any], *, root: Path | None = None) -> None:
    import streamlit as st

    errors: list[str] = []
    if root is not None and (root / "story.json").is_file():
        try:
            story_raw = (root / "story.json").read_bytes()
            story = strict_json_bytes(story_raw)
            if isinstance(story, Mapping):
                errors = validate_image_prompt_plan(plan, story, story_raw)
            else:
                errors = ["story.json root phải là object"]
        except (OSError, UnicodeError, ValueError) as exc:
            errors = [str(exc)]
    if errors:
        st.error(f"Kế hoạch ảnh không hợp lệ: {len(errors)} lỗi")
        st.markdown("\n".join(f"- {error}" for error in errors))
    else:
        st.success("Kế hoạch ảnh khớp closed schema và source story." if root else "Đã nạp kế hoạch ảnh; chưa có story bytes để bind hash.")
    raw_assets = plan.get("assets")
    assets: list[Any] = raw_assets if isinstance(raw_assets, list) else []
    left, middle, right = st.columns(3)
    left.metric("Asset", len(assets))
    middle.metric("Nhân vật khóa", len(plan.get("character_locks", [])) if isinstance(plan.get("character_locks"), list) else 0)
    right.metric("Mode", str(plan.get("image_mode") or "—"))
    st.dataframe([
        {"ID": row.get("asset_id"), "Tệp": row.get("basename"), "Vai trò": row.get("role"),
         "Script": ", ".join(str(value) for value in row.get("source_script_ids", [])),
         "Nhân vật": ", ".join(str(value) for value in row.get("character_ids", []))}
        for row in assets if isinstance(row, Mapping)
    ], hide_index=True, width="stretch")
    with st.expander("Style và character locks"):
        st.write(str(plan.get("style_lock") or ""))
        st.json(plan.get("character_locks", []), expanded=False)


__all__ = [
    "ASSET_FIELDS", "CHARACTER_FIELDS", "PROMPT_ENCODING_FIELDS", "ROOT_FIELDS",
    "ROOT_FIELDS_V1", "render_image_prompt_plan", "validate_image_prompt_bytes",
    "validate_image_prompt_plan",
]
