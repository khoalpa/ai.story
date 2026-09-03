"""Deterministic structural validation for canonical video_prompts.json."""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, cast

from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.video_voice import (
    VOICE_PLAN_FIELDS,
    VOICE_SEGMENT_FIELDS,
    VOICE_STRATEGY_FIELDS,
    build_voice_plan,
    native_audio_prompt,
    source_segments,
)
from studio.workflow_package import safe_name

ROOT_FIELDS = ("schema_version", "generator_target", "source_binding", "project", "global_continuity_lock", "clips", "validation")
VOICE_ROOT_FIELDS = ("schema_version", "generator_target", "source_binding", "project", "voice_strategy", "global_continuity_lock", "clips", "validation")
TARGET_FIELDS = ("family", "preferred_model", "prompt_language", "capability_profile")
CAPABILITY_FIELDS = ("aspect_ratio", "clip_duration_seconds", "audio_mode", "requested_continuity_mode", "reference_images", "first_last_frame", "video_extension")
CAPABILITY_EVIDENCE_FIELDS = ("supported", "status", "evidence_locator")
BINDING_FIELDS = ("story_sha256", "story_validation_sha256", "package_quality_report_sha256", "character_continuity_source_digest_sha256", "character_set_digest_sha256")
PROJECT_FIELDS = ("title", "series", "episode", "active_profile", "coverage_mode", "total_story_duration_seconds", "planned_covered_duration_seconds", "planned_video_duration_seconds", "clip_count", "derived_scene_count", "coverage_exclusions")
GLOBAL_FIELDS = ("visual_style", "cinematography", "color_pipeline", "character_identity_rules", "location_rules", "prop_rules", "forbidden_changes", "derived_scene_registry")
CLIP_FIELDS = ("clip_id", "sequence_index", "zone", "derived_scene_id", "continuity_take_id", "source_script", "generation_variants", "duration_seconds", "usable_span_seconds", "aspect_ratio", "reference_inputs", "continuity_in", "primary_action", "visual_delta", "terminal_handoff", "prompt", "audio_prompt", "avoid", "continuity_out", "state_change_records", "transition_type")
VOICE_CLIP_FIELDS = ("clip_id", "sequence_index", "zone", "derived_scene_id", "continuity_take_id", "source_script", "generation_variants", "duration_seconds", "usable_span_seconds", "aspect_ratio", "reference_inputs", "continuity_in", "primary_action", "visual_delta", "terminal_handoff", "prompt", "voice_plan", "audio_prompt", "avoid", "continuity_out", "state_change_records", "transition_type")
SOURCE_FIELDS = ("start_item_index", "start_word_offset", "end_item_index", "end_word_offset", "start_time_seconds", "end_time_seconds", "pause_only", "source_text_digest_sha256")
VARIANT_FIELDS = ("requested_continuity_mode", "preferred_mode", "fallback_modes", "portable_mode", "capability_status", "selection_basis")
REFERENCE_FIELDS = ("character_images", "previous_clip_id", "previous_last_frame_required", "previous_output_last_frame", "previous_output_video_required")
VALIDATION_FIELDS = ("schema_status", "source_binding_status", "timeline_derivation_status", "scene_derivation_status", "reference_router_status", "character_only_reference_status", "coverage_status", "continuity_status", "identity_reference_status", "prompt_budget_status", "prompt_atomicity_status", "no_invented_event_status", "anti_repeat_status", "safety_status", "fixture_status", "output_digest_sha256", "status")
REQUIRED_EXPORT_GATES = ("schema", "source_binding", "semantic_continuity")
ADVISORY_EXPORT_GATES = ("no_invented_event", "safety")


def export_gate_eligible(gate_statuses: Mapping[str, str], errors: list[str]) -> bool:
    """Apply export policy: local deterministic gates block; advisory certification does not."""
    return not errors and all(gate_statuses.get(name) == "PASS" for name in REQUIRED_EXPORT_GATES)


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


def semantic_continuity_gate(clips: list[Any]) -> tuple[str, list[str]]:
    """Deterministically compare the serialized state chain within each scene."""
    continuity_keys = (
        "character_state", "wardrobe_state", "location_state", "prop_state",
        "screen_direction", "camera_state",
    )
    if not clips or not all(isinstance(clip, dict) for clip in clips):
        return "NOT_VERIFIED", []
    failures = []
    for previous, current in zip(clips, clips[1:]):
        if previous.get("derived_scene_id") != current.get("derived_scene_id"):
            continue
        continuity_out = _object(previous.get("continuity_out"))
        continuity_in = _object(current.get("continuity_in"))
        if ({key: continuity_out.get(key) for key in continuity_keys}
                != {key: continuity_in.get(key) for key in continuity_keys}):
            failures.append(
                f"{previous.get('clip_id', '—')} → {current.get('clip_id', '—')}"
            )
    return ("FAIL", failures) if failures else ("PASS", [])


def _source_digest(script: list[Any], source: Mapping[str, Any]) -> str:
    """Hash one half-open story span using the prompt's canonical token format."""
    start_item = source["start_item_index"]
    end_item = source["end_item_index"]
    start_word = source["start_word_offset"]
    end_word = source["end_word_offset"]
    segments = []
    for item_index in range(start_item, end_item + 1):
        item = script[item_index]
        tokens = str(item.get("text", "")).split()
        left = start_word if item_index == start_item else 0
        right = end_word if item_index == end_item else len(tokens)
        token_slice = " ".join(tokens[left:right])
        segments.append(
            f"{item_index}\x1f{left}\x1f{right}\x1f"
            f"{unicodedata.normalize('NFC', token_slice)}\x1f"
            f"{str(bool(source.get('pause_only'))).lower()}"
        )
    return hashlib.sha256("\x1e".join(segments).encode("utf-8")).hexdigest()


def normalize_video_prompt_plan(plan: Mapping[str, Any], story: Mapping[str, Any], *,
                                contract: PromptContract | None = None) -> dict[str, Any]:
    """Repair mechanical Stage 4 fields without changing creative semantics.

    Source boundaries must already describe a valid, contiguous story partition.  The
    function deliberately refuses to invent boundaries or mark validation gates PASS.
    """
    contract = contract or load_prompt_contract()
    normalized = deepcopy(dict(plan))
    script = story.get("script")
    clips = normalized.get("clips")
    if not isinstance(script, list) or not all(isinstance(item, dict) for item in script):
        raise ValueError("story.json.script không phải array object hợp lệ")
    if not isinstance(clips, list) or not clips:
        raise ValueError("video_prompts.json không có clips để hậu xử lý")

    ratio_aliases = {"16:9": "LANDSCAPE_16_9", "9:16": "PORTRAIT_9_16"}
    target = normalized.get("generator_target")
    capability = target.get("capability_profile") if isinstance(target, dict) else None
    if isinstance(capability, dict):
        capability["aspect_ratio"] = ratio_aliases.get(
            capability.get("aspect_ratio"), capability.get("aspect_ratio")
        )

    global_lock = normalized.get("global_continuity_lock")
    if isinstance(global_lock, dict):
        for key in GLOBAL_FIELDS[:-1]:
            value = global_lock.get(key)
            if isinstance(value, str) and value.strip():
                global_lock[key] = [value]

    voice_strategy = normalized.get("voice_strategy")

    word_counts = [len(str(item.get("text", "")).split()) for item in script]
    bases: list[int] = []
    total_words = 0
    for count in word_counts:
        bases.append(total_words)
        total_words += count

    previous_end = 0
    for index, clip in enumerate(clips, 1):
        if not isinstance(clip, dict) or not isinstance(clip.get("source_script"), dict):
            raise ValueError(f"Clip {index}: thiếu source_script hợp lệ")
        source = clip["source_script"]
        values = [source.get(key) for key in (
            "start_item_index", "start_word_offset", "end_item_index", "end_word_offset"
        )]
        if not all(type(value) is int and value >= 0 for value in values):
            raise ValueError(f"Clip {index}: offset phải là integer không âm")
        start_item, start_word, end_item, end_word = values
        if not start_item <= end_item < len(script):
            raise ValueError(f"Clip {index}: item offset nằm ngoài story.json")
        if start_word > word_counts[start_item] or end_word > word_counts[end_item]:
            raise ValueError(f"Clip {index}: word offset nằm ngoài story.json")
        start_global = bases[start_item] + start_word
        end_global = bases[end_item] + end_word
        if start_global != previous_end or end_global <= start_global:
            raise ValueError(f"Clip {index}: source span không liên tục hoặc rỗng")
        previous_end = end_global

        clip["aspect_ratio"] = ratio_aliases.get(clip.get("aspect_ratio"), clip.get("aspect_ratio"))
        source["source_text_digest_sha256"] = _source_digest(script, source)
        if isinstance(voice_strategy, dict):
            voice_plan = build_voice_plan(script, source)
            clip["voice_plan"] = voice_plan
            audio_prompt = str(clip.get("audio_prompt") or "")
            if "Background below voice:" in audio_prompt:
                ambience = audio_prompt.split("Background below voice:", 1)[1].split(". No music", 1)[0]
            else:
                ambience = "Quiet source-consistent ambience and natural foley"
            clip["audio_prompt"] = native_audio_prompt(voice_plan, voice_strategy, ambience)

    project = normalized.get("project")
    if isinstance(project, dict) and project.get("coverage_mode") == "FULL_STORY" and previous_end != total_words:
        raise ValueError("FULL_STORY không phủ toàn bộ token của story.json")
    validation = normalized.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("video_prompts.validation không hợp lệ")
    validation["output_digest_sha256"] = canonical_output_digest(normalized)
    return normalized


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

    if tuple(plan) not in {ROOT_FIELDS, VOICE_ROOT_FIELDS} or plan.get("schema_version") != contract.video_prompt_schema_version:
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
    allowed_character_images: set[str] = set()
    if story_document is not None and isinstance(story_document.get("characters"), list):
        for character in story_document["characters"]:
            if isinstance(character, dict):
                path = _object(character.get("reference_asset")).get("reference_image")
                if isinstance(path, str):
                    allowed_character_images.add(path)
    voice_strategy = _object(plan.get("voice_strategy"))
    if voice_strategy:
        exact(voice_strategy, VOICE_STRATEGY_FIELDS, "voice_strategy")
        if voice_strategy.get("audio_mode") != "NATIVE_GENERATED_VOICE" or voice_strategy.get("language") != "vi-VN":
            errors.append("voice_strategy audio_mode/language không hợp lệ.")
        profiles = voice_strategy.get("voice_profiles")
        if not isinstance(profiles, list) or not profiles:
            errors.append("voice_strategy.voice_profiles phải là array không rỗng.")
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
    previous_word_end = 0
    story_word_bases: list[int] = []
    story_total_words = 0
    if story_document is not None and isinstance(story_document.get("script"), list):
        for item in story_document["script"]:
            story_word_bases.append(story_total_words)
            story_total_words += len(str(item.get("text", "")).split()) if isinstance(item, dict) else 0
    normalized_prompts: set[str] = set()
    scene_ids = {item.get("derived_scene_id", item.get("scene_id")) for item in registry if isinstance(item, dict)}
    for index, clip in enumerate(clips, 1):
        exact(clip, VOICE_CLIP_FIELDS if voice_strategy else CLIP_FIELDS, f"clip {index}")
        source = exact(clip.get("source_script"), SOURCE_FIELDS, f"clip {index}.source_script")
        variants = exact(clip.get("generation_variants"), VARIANT_FIELDS, f"clip {index}.generation_variants")
        refs = exact(clip.get("reference_inputs"), REFERENCE_FIELDS, f"clip {index}.reference_inputs")
        if clip.get("clip_id") != f"clip_{index:04d}" or clip.get("sequence_index") != index:
            errors.append(f"Clip {index}: ID/sequence không liên tục.")
        duration = clip.get("duration_seconds")
        usable = clip.get("usable_span_seconds")
        duration_number = float(cast(float, duration)) if _finite(duration, positive=True) else None
        usable_number = float(cast(float, usable)) if _finite(usable, positive=True) else None
        if (duration not in contract.video_clip_durations or duration_number is None
                or usable_number is None or usable_number > duration_number):
            errors.append(f"Clip {index}: duration/usable_span không hợp lệ.")
        else:
            total += duration_number
        start = source.get("start_time_seconds")
        end = source.get("end_time_seconds")
        start_number = float(cast(float, start)) if _finite(start) else None
        end_number = float(cast(float, end)) if _finite(end, positive=True) else None
        if (start_number is None or end_number is None
                or start_number >= end_number or start_number < previous_end):
            errors.append(f"Clip {index}: source interval không hợp lệ.")
        else:
            if project.get("coverage_mode") == "FULL_STORY" and not math.isclose(start_number, previous_end, abs_tol=.0005, rel_tol=0):
                errors.append(f"Clip {index}: FULL_STORY có khoảng trống nguồn.")
            previous_end = end_number
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
        audio_word_limit = (contract.video_prompt_hard_max_words if voice_strategy
                            else contract.video_audio_prompt_hard_max_words)
        if prompt_words > contract.video_prompt_hard_max_words or audio_words > audio_word_limit:
            errors.append(f"Clip {index}: vượt hard word budget.")
        if (not isinstance(avoid, list) or not all(isinstance(item, str) for item in avoid)
                or len(avoid) > contract.video_avoid_item_max_count
                or len(avoid) != len(set(avoid))):
            errors.append(f"Clip {index}: avoid count/uniqueness không hợp lệ.")
        normalized_prompt = unicodedata.normalize("NFC", str(clip.get("prompt", "")))
        if normalized_prompt in normalized_prompts:
            errors.append(f"Clip {index}: prompt trùng exact.")
        normalized_prompts.add(normalized_prompt)
        character_images = refs.get("character_images")
        if (not isinstance(character_images, list) or not all(isinstance(item, str) for item in character_images)
                or len(character_images) > contract.video_max_character_references_per_clip
                or len(character_images) != len(set(character_images))):
            errors.append(f"Clip {index}: character_images vượt giới hạn hoặc trùng.")
        names = character_images if isinstance(character_images, list) else []
        for name in names:
            if (name.startswith(("landscape/", "portrait/")) or "://" in name
                    or name not in allowed_character_images):
                errors.append(f"Clip {index}: PACKAGED_SCENE_REFERENCE_FORBIDDEN: {name}")
            if (root is not None or members is not None) and name is not None and source_bytes(name) is None:
                errors.append(f"Clip {index}: thiếu ảnh tham chiếu {name!r}.")
        if variants.get("requested_continuity_mode") == "CHAINED_LAST_FRAME":
            previous_clip = clips[index - 2] if index > 1 else None
            same_scene = (isinstance(previous_clip, dict)
                          and previous_clip.get("derived_scene_id") == clip.get("derived_scene_id"))
            expected_previous_id = previous_clip.get("clip_id") if same_scene else None
            if refs.get("previous_clip_id") != expected_previous_id:
                errors.append(f"Clip {index}: previous_clip_id không bind clip trước.")
        if story_document is not None:
            script = story_document.get("script")
            start_item, end_item = source.get("start_item_index"), source.get("end_item_index")
            start_word, end_word = source.get("start_word_offset"), source.get("end_word_offset")
            offsets_are_integers = all(
                type(value) is int and value >= 0
                for value in (start_item, end_item, start_word, end_word)
            )
            if not isinstance(script, list) or not offsets_are_integers:
                errors.append(f"Clip {index}: item/word offsets không hợp lệ.")
            else:
                start_item_int = cast(int, start_item)
                end_item_int = cast(int, end_item)
                start_word_int = cast(int, start_word)
                end_word_int = cast(int, end_word)
                if not start_item_int <= end_item_int < len(script):
                    errors.append(f"Clip {index}: item/word offsets không hợp lệ.")
                else:
                    valid_offsets = True
                    for item_index in range(start_item_int, end_item_int + 1):
                        item = script[item_index]
                        tokens = str(item.get("text", "")).split() if isinstance(item, dict) else []
                        left = start_word_int if item_index == start_item_int else 0
                        right = end_word_int if item_index == end_item_int else len(tokens)
                        if left > right or right > len(tokens):
                            valid_offsets = False
                            break
                    digest = _source_digest(script, source) if valid_offsets else None
                    if not valid_offsets or source.get("source_text_digest_sha256") != digest:
                        errors.append(f"Clip {index}: source_text_digest/offset không khớp story.")
                    if valid_offsets and voice_strategy:
                        voice_plan = exact(clip.get("voice_plan"), VOICE_PLAN_FIELDS, f"clip {index}.voice_plan")
                        expected_segments = source_segments(script, source)
                        segments = voice_plan.get("segments")
                        if not isinstance(segments, list) or len(segments) != len(expected_segments):
                            errors.append(f"Clip {index}: voice segments không khớp source span.")
                        else:
                            for position, (segment, expected) in enumerate(zip(segments, expected_segments), 1):
                                exact(segment, VOICE_SEGMENT_FIELDS, f"clip {index}.voice_plan.segment {position}")
                                if segment != expected:
                                    errors.append(f"Clip {index}: voice segment {position} không khớp story.json.")
                            joined = unicodedata.normalize("NFC", "\n".join(item["text"] for item in expected_segments))
                            if voice_plan.get("source_text_sha256") != hashlib.sha256(joined.encode("utf-8")).hexdigest():
                                errors.append(f"Clip {index}: voice source digest không khớp.")
                        if voice_plan.get("allow_paraphrase") is not False or voice_plan.get("language") != "vi-VN":
                            errors.append(f"Clip {index}: voice plan phải giữ nguyên lời tiếng Việt.")
                        audio_text = str(clip.get("audio_prompt") or "").casefold()
                        if "no generated narration" in audio_text or "no generated narration or dialogue" in audio_text:
                            errors.append(f"Clip {index}: audio prompt mâu thuẫn native voice.")
                    if valid_offsets:
                        start_global = story_word_bases[start_item_int] + start_word_int
                        end_global = story_word_bases[end_item_int] + end_word_int
                        if end_global <= start_global:
                            errors.append(f"Clip {index}: source span rỗng hoặc đảo chiều.")
                        if project.get("coverage_mode") == "FULL_STORY" and start_global != previous_word_end:
                            errors.append(f"Clip {index}: source span không liên tục với clip trước.")
                        previous_word_end = end_global
        rows.append({"Clip": clip.get("clip_id", index), "Zone": clip.get("zone", "—"), "Scene": clip.get("derived_scene_id", "—"), "Bắt đầu (s)": start, "Kết thúc (s)": end, "Độ dài video (s)": duration, "Tỷ lệ": clip.get("aspect_ratio", "—")})

    planned = project.get("planned_video_duration_seconds")
    if not _finite(planned) or not math.isclose(total, float(cast(float, planned)), abs_tol=.0005, rel_tol=0):
        errors.append("planned_video_duration_seconds không bằng tổng duration clip.")
    if project.get("coverage_mode") == "FULL_STORY":
        story_duration = project.get("total_story_duration_seconds")
        if (not _finite(story_duration)
                or not math.isclose(previous_end, float(cast(float, story_duration)), abs_tol=.0005, rel_tol=0)
                or project.get("coverage_exclusions") != []):
            errors.append("FULL_STORY phải phủ toàn truyện và không có exclusions.")
        if story_document is not None and previous_word_end != story_total_words:
            errors.append("FULL_STORY không phủ đúng toàn bộ token của story.json.")
    validation = exact(plan.get("validation"), VALIDATION_FIELDS, "validation")
    if any(validation.get(key) != "PASS" for key in VALIDATION_FIELDS if key not in {"output_digest_sha256"}):
        errors.append("validation components/aggregate phải PASS.")
    try:
        if validation.get("output_digest_sha256") != canonical_output_digest(plan):
            errors.append("validation.output_digest_sha256 không khớp canonical JSON.")
    except (TypeError, ValueError):
        errors.append("Không thể tính output_digest_sha256.")
    continuity_status, continuity_failures = semantic_continuity_gate(clips)
    if continuity_failures:
        errors.append("Semantic continuity không khớp: " + ", ".join(continuity_failures[:5]))
    if errors and continuity_status == "PASS":
        continuity_status = "NOT_VERIFIED"
    gate_statuses = {
        "schema": "FAIL" if errors else "PASS",
        "source_binding": "FAIL" if any(c["status"] == "FAIL" for c in checks) else
                          "NOT_VERIFIED" if any(c["status"] == "NOT_VERIFIED" for c in checks) else "PASS",
        "semantic_continuity": continuity_status,
        "no_invented_event": "NOT_VERIFIED",
        "safety": "NOT_VERIFIED",
    }
    export_eligible = export_gate_eligible(gate_statuses, errors)
    return {"status": "FAIL" if errors else "NOT_VERIFIED" if not export_eligible else "PASS",
            "errors": errors, "checks": checks, "gate_statuses": gate_statuses,
            "required_export_gates": REQUIRED_EXPORT_GATES,
            "advisory_export_gates": ADVISORY_EXPORT_GATES,
            "export_eligible": export_eligible, "rows": rows, "clips": clips, "duration": total,
            "needs_confirmation": project.get("coverage_mode") == "FULL_STORY" and len(clips) > 120}


__all__ = ["ADVISORY_EXPORT_GATES", "REQUIRED_EXPORT_GATES", "canonical_output_digest", "export_gate_eligible",
           "normalize_video_prompt_plan", "semantic_continuity_gate", "validate_video_prompt_plan"]
