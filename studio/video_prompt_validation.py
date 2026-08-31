"""Deterministic structural validation for canonical video_prompts.json."""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.workflow_package import safe_name

ROOT_FIELDS = ("schema_version", "generator_target", "source_binding", "project", "global_continuity_lock", "clips", "validation")
TARGET_FIELDS = ("family", "preferred_model", "prompt_language", "capability_profile")
CAPABILITY_FIELDS = ("aspect_ratio", "clip_duration_seconds", "audio_mode", "requested_continuity_mode", "reference_images", "first_last_frame", "video_extension")
CAPABILITY_EVIDENCE_FIELDS = ("supported", "status", "evidence_locator")
BINDING_FIELDS = ("story_sha256", "story_validation_sha256", "package_quality_report_sha256", "visual_continuity_source_digest_sha256", "character_set_digest_sha256", "landscape_set_digest_sha256", "portrait_set_digest_sha256")
PROJECT_FIELDS = ("title", "series", "episode", "active_profile", "coverage_mode", "total_story_duration_seconds", "planned_covered_duration_seconds", "planned_video_duration_seconds", "clip_count", "derived_scene_count", "coverage_exclusions")
GLOBAL_FIELDS = ("visual_style", "cinematography", "color_pipeline", "character_identity_rules", "location_rules", "prop_rules", "forbidden_changes", "derived_scene_registry")
CLIP_FIELDS = ("clip_id", "sequence_index", "zone", "derived_scene_id", "continuity_take_id", "source_script", "generation_variants", "duration_seconds", "usable_span_seconds", "aspect_ratio", "reference_inputs", "continuity_in", "primary_action", "visual_delta", "terminal_handoff", "prompt", "audio_prompt", "avoid", "continuity_out", "state_change_records", "transition_type")
SOURCE_FIELDS = ("start_item_index", "start_word_offset", "end_item_index", "end_word_offset", "start_time_seconds", "end_time_seconds", "pause_only", "source_text_digest_sha256")
VARIANT_FIELDS = ("requested_continuity_mode", "preferred_mode", "fallback_modes", "portable_mode", "capability_status", "selection_basis")
REFERENCE_FIELDS = ("primary_frame", "zone_reference_frame", "character_images", "previous_clip_id", "previous_last_frame_required", "previous_output_last_frame", "previous_output_video_required", "target_last_frame")
VALIDATION_FIELDS = ("schema_status", "source_binding_status", "timeline_derivation_status", "scene_derivation_status", "reference_router_status", "coverage_status", "continuity_status", "identity_reference_status", "prompt_budget_status", "prompt_atomicity_status", "no_invented_event_status", "anti_repeat_status", "safety_status", "fixture_status", "output_digest_sha256", "status")


def _object(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _finite(value: Any, *, positive: bool = False) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and (value > 0 if positive else value >= 0)


def canonical_output_digest(plan: Mapping[str, Any]) -> str:
    clone = json.loads(json.dumps(plan, ensure_ascii=False, allow_nan=False))
    validation = clone.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("validation phải là object")
    validation["output_digest_sha256"] = None
    text = unicodedata.normalize("NFC", json.dumps(clone, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_video_prompt_plan(plan: Mapping[str, Any], *, contract: PromptContract | None = None,
                               root: Path | None = None, members: Mapping[str, bytes] | None = None) -> dict[str, Any]:
    contract = contract or load_prompt_contract()
    errors: list[str] = []
    checks: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []

    def exact(value: Any, fields: tuple[str, ...], label: str) -> Mapping[str, Any]:
        obj = _object(value)
        if tuple(obj) != fields:
            errors.append(f"{label}: field/order không đúng schema.")
        return obj

    def source_bytes(name: str) -> bytes | None:
        if not safe_name(name):
            return None
        if members is not None:
            return members.get(name)
        if root is not None:
            path = root / name
            if path.resolve().is_relative_to(root.resolve()) and path.is_file() and path.stat().st_size <= 64 * 1024 * 1024:
                return path.read_bytes()
        return None

    if tuple(plan) != ROOT_FIELDS or plan.get("schema_version") != contract.video_prompt_schema_version:
        errors.append(f"Root schema/field order không đúng video prompt v{contract.video_prompt_schema_version}.")
    target = exact(plan.get("generator_target"), TARGET_FIELDS, "generator_target")
    capability = exact(target.get("capability_profile"), CAPABILITY_FIELDS, "capability_profile")
    if target.get("family") != "VEO" or not isinstance(target.get("preferred_model"), str) or not target.get("preferred_model"):
        errors.append("generator_target family/model không hợp lệ.")
    if target.get("prompt_language") not in contract.video_prompt_languages:
        errors.append("generator_target.prompt_language ngoài enum.")
    if capability.get("aspect_ratio") not in contract.video_aspect_ratios or capability.get("clip_duration_seconds") not in contract.video_clip_durations or capability.get("audio_mode") not in contract.video_audio_modes or capability.get("requested_continuity_mode") not in contract.video_continuity_modes:
        errors.append("capability_profile có giá trị ngoài enum canonical.")
    for key in ("reference_images", "first_last_frame", "video_extension"):
        item = exact(capability.get(key), CAPABILITY_EVIDENCE_FIELDS, f"capability_profile.{key}")
        if type(item.get("supported")) is not bool or item.get("status") not in contract.video_capability_statuses:
            errors.append(f"capability_profile.{key}: evidence không hợp lệ.")
        locator = item.get("evidence_locator")
        if not ((item.get("status") == "NOT_VERIFIED" and locator is None) or isinstance(locator, str) and bool(locator)):
            errors.append(f"capability_profile.{key}: evidence_locator không hợp lệ.")

    binding = exact(plan.get("source_binding"), BINDING_FIELDS, "source_binding")
    story_document: Mapping[str, Any] | None = None
    for name, key in (("story.json", "story_sha256"), ("story_validation.json", "story_validation_sha256"), ("package_quality_report.json", "package_quality_report_sha256")):
        raw = source_bytes(name)
        status = "NOT_VERIFIED" if raw is None else "PASS" if hashlib.sha256(raw).hexdigest() == binding.get(key) else "FAIL"
        checks.append({"check": name, "status": status, "detail": "Exact source SHA-256"})
        if status == "FAIL":
            errors.append(f"source_binding.{key} không khớp exact bytes.")
        if name == "story.json" and raw is not None:
            try:
                parsed = json.loads(raw.decode("utf-8"))
                story_document = parsed if isinstance(parsed, dict) else None
            except (UnicodeError, json.JSONDecodeError):
                errors.append("story.json không parse được để kiểm source span.")

    project = exact(plan.get("project"), PROJECT_FIELDS, "project")
    global_lock = exact(plan.get("global_continuity_lock"), GLOBAL_FIELDS, "global_continuity_lock")
    for key in GLOBAL_FIELDS[:-1]:
        if not isinstance(global_lock.get(key), list):
            errors.append(f"global_continuity_lock.{key} phải là array.")
    registry = global_lock.get("derived_scene_registry")
    if not isinstance(registry, list):
        errors.append("derived_scene_registry phải là array.")
        registry = []
    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips or not all(isinstance(c, dict) for c in clips):
        errors.append("clips phải là array object không rỗng.")
        clips = []
    if project.get("coverage_mode") not in contract.video_coverage_modes:
        errors.append("project.coverage_mode ngoài enum.")
    if project.get("clip_count") != len(clips) or project.get("derived_scene_count") != len(registry):
        errors.append("project clip_count/derived_scene_count không khớp.")

    total = 0.0
    previous_end = 0.0
    normalized_prompts: set[str] = set()
    scene_ids = {item.get("derived_scene_id", item.get("scene_id")) for item in registry if isinstance(item, dict)}
    for index, clip in enumerate(clips, 1):
        exact(clip, CLIP_FIELDS, f"clip {index}")
        source = exact(clip.get("source_script"), SOURCE_FIELDS, f"clip {index}.source_script")
        variants = exact(clip.get("generation_variants"), VARIANT_FIELDS, f"clip {index}.generation_variants")
        refs = exact(clip.get("reference_inputs"), REFERENCE_FIELDS, f"clip {index}.reference_inputs")
        if clip.get("clip_id") != f"clip_{index:04d}" or clip.get("sequence_index") != index:
            errors.append(f"Clip {index}: ID/sequence không liên tục.")
        duration = clip.get("duration_seconds")
        usable = clip.get("usable_span_seconds")
        if duration not in contract.video_clip_durations or not _finite(usable, positive=True) or usable > duration:
            errors.append(f"Clip {index}: duration/usable_span không hợp lệ.")
        else:
            total += duration
        start, end = source.get("start_time_seconds"), source.get("end_time_seconds")
        if not _finite(start) or not _finite(end, positive=True) or start >= end or start < previous_end:
            errors.append(f"Clip {index}: source interval không hợp lệ.")
        else:
            if project.get("coverage_mode") == "FULL_STORY" and not math.isclose(start, previous_end, abs_tol=.0005, rel_tol=0):
                errors.append(f"Clip {index}: FULL_STORY có khoảng trống nguồn.")
            previous_end = end
        if variants.get("requested_continuity_mode") not in contract.video_continuity_modes or variants.get("preferred_mode") not in contract.video_generation_modes or variants.get("portable_mode") != "TEXT_TO_VIDEO" or variants.get("capability_status") not in contract.video_capability_statuses:
            errors.append(f"Clip {index}: generation_variants ngoài enum.")
        fallback = variants.get("fallback_modes")
        if not isinstance(fallback, list) or len(fallback) != len(set(fallback)) or any(v not in contract.video_generation_modes for v in fallback) or variants.get("preferred_mode") in fallback:
            errors.append(f"Clip {index}: fallback_modes không hợp lệ.")
        if clip.get("aspect_ratio") not in contract.video_aspect_ratios or clip.get("transition_type") not in contract.video_transition_types:
            errors.append(f"Clip {index}: aspect_ratio/transition_type ngoài enum.")
        if clip.get("derived_scene_id") not in scene_ids:
            errors.append(f"Clip {index}: derived_scene_id không resolve registry.")
        for key in ("primary_action", "visual_delta", "terminal_handoff", "prompt", "audio_prompt"):
            if not isinstance(clip.get(key), str) or not clip.get(key):
                errors.append(f"Clip {index}: {key} phải là string không rỗng.")
        prompt_words = len(str(clip.get("prompt", "")).split())
        audio_words = len(str(clip.get("audio_prompt", "")).split())
        avoid = clip.get("avoid")
        if prompt_words > contract.video_prompt_hard_max_words or audio_words > contract.video_audio_prompt_hard_max_words:
            errors.append(f"Clip {index}: vượt hard word budget.")
        if (not isinstance(avoid, list) or not all(isinstance(item, str) for item in avoid)
                or len(avoid) > contract.video_avoid_item_max_count
                or len(avoid) != len(set(avoid))):
            errors.append(f"Clip {index}: avoid count/uniqueness không hợp lệ.")
        normalized_prompt = unicodedata.normalize("NFC", str(clip.get("prompt", "")))
        if normalized_prompt in normalized_prompts:
            errors.append(f"Clip {index}: prompt trùng exact.")
        normalized_prompts.add(normalized_prompt)
        names = [refs.get("zone_reference_frame"), refs.get("primary_frame"), refs.get("target_last_frame")]
        names += refs.get("character_images", []) if isinstance(refs.get("character_images"), list) else [None]
        character_images = refs.get("character_images")
        if (not isinstance(character_images, list) or not all(isinstance(item, str) for item in character_images)
                or len(character_images) > contract.video_max_character_references_per_clip
                or len(character_images) != len(set(character_images))):
            errors.append(f"Clip {index}: character_images vượt giới hạn hoặc trùng.")
        for name in names:
            if (root is not None or members is not None) and name is not None and source_bytes(name) is None:
                errors.append(f"Clip {index}: thiếu ảnh tham chiếu {name!r}.")
        if index > 1 and variants.get("requested_continuity_mode") == "CHAINED_LAST_FRAME":
            if refs.get("previous_clip_id") != f"clip_{index - 1:04d}":
                errors.append(f"Clip {index}: previous_clip_id không bind clip trước.")
        if story_document is not None:
            script = story_document.get("script")
            start_item, end_item = source.get("start_item_index"), source.get("end_item_index")
            start_word, end_word = source.get("start_word_offset"), source.get("end_word_offset")
            if not (isinstance(script, list) and all(type(v) is int and v >= 0 for v in (start_item, end_item, start_word, end_word))
                    and start_item <= end_item < len(script)):
                errors.append(f"Clip {index}: item/word offsets không hợp lệ.")
            else:
                segments = []
                valid_offsets = True
                for item_index in range(start_item, end_item + 1):
                    item = script[item_index]
                    tokens = str(item.get("text", "")).split() if isinstance(item, dict) else []
                    left = start_word if item_index == start_item else 0
                    right = end_word if item_index == end_item else len(tokens)
                    if left > right or right > len(tokens):
                        valid_offsets = False
                        break
                    token_slice = " ".join(tokens[left:right])
                    segments.append(f"{item_index}\x1f{left}\x1f{right}\x1f{unicodedata.normalize('NFC', token_slice)}\x1f{str(bool(source.get('pause_only'))).lower()}")
                digest = hashlib.sha256("\x1e".join(segments).encode("utf-8")).hexdigest()
                if not valid_offsets or source.get("source_text_digest_sha256") != digest:
                    errors.append(f"Clip {index}: source_text_digest/offset không khớp story.")
        rows.append({"Clip": clip.get("clip_id", index), "Zone": clip.get("zone", "—"), "Scene": clip.get("derived_scene_id", "—"), "Bắt đầu (s)": start, "Kết thúc (s)": end, "Độ dài video (s)": duration, "Tỷ lệ": clip.get("aspect_ratio", "—")})

    planned = project.get("planned_video_duration_seconds")
    if not _finite(planned) or not math.isclose(total, planned, abs_tol=.0005, rel_tol=0):
        errors.append("planned_video_duration_seconds không bằng tổng duration clip.")
    if project.get("coverage_mode") == "FULL_STORY":
        if not math.isclose(previous_end, project.get("total_story_duration_seconds", -1), abs_tol=.0005, rel_tol=0) or project.get("coverage_exclusions") != []:
            errors.append("FULL_STORY phải phủ toàn truyện và không có exclusions.")
    validation = exact(plan.get("validation"), VALIDATION_FIELDS, "validation")
    if any(validation.get(key) != "PASS" for key in VALIDATION_FIELDS if key not in {"output_digest_sha256"}):
        errors.append("validation components/aggregate phải PASS.")
    try:
        if validation.get("output_digest_sha256") != canonical_output_digest(plan):
            errors.append("validation.output_digest_sha256 không khớp canonical JSON.")
    except (TypeError, ValueError):
        errors.append("Không thể tính output_digest_sha256.")
    gate_statuses = {
        "schema": "FAIL" if errors else "PASS",
        "source_binding": "FAIL" if any(c["status"] == "FAIL" for c in checks) else
                          "NOT_VERIFIED" if any(c["status"] == "NOT_VERIFIED" for c in checks) else "PASS",
        "semantic_continuity": "NOT_VERIFIED",
        "no_invented_event": "NOT_VERIFIED",
        "safety": "NOT_VERIFIED",
    }
    export_eligible = not errors and all(value == "PASS" for value in gate_statuses.values())
    return {"status": "FAIL" if errors else "NOT_VERIFIED" if not export_eligible else "PASS",
            "errors": errors, "checks": checks, "gate_statuses": gate_statuses,
            "export_eligible": export_eligible, "rows": rows, "clips": clips, "duration": total,
            "needs_confirmation": project.get("coverage_mode") == "FULL_STORY" and len(clips) > 120}


__all__ = ["canonical_output_digest", "validate_video_prompt_plan"]
