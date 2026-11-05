"""Validate source spans and references in v4 story video plans."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from studio.workflow_package import read_json, safe_name

V4_FIELDS = {"schema_version", "source_mode", "target_model", "coverage", "timing_basis", "timing_config", "clips", "limitations"}
CLIP_FIELDS = {"clip_id", "source_spans", "estimated_seconds", "aspect_ratio", "reference_paths", "prompt", "narration", "audio_note", "transition"}
TIMING_FIELDS = {"method_id", "rate_per_minute", "evidence_locator"}


def validate_v4_plan(
    plan: Mapping[str, Any], *, root: Path | None, members: Mapping[str, bytes] | None,
) -> dict[str, Any]:
    errors: list[str] = []
    raw_clips = plan.get("clips")
    clips = raw_clips if isinstance(raw_clips, list) else []
    if not clips:
        errors.append("clips phải là array không rỗng")
    if plan.get("schema_version") != "4.1.3":
        errors.append("schema_version phải là 4.1.3")
    for key, allowed in (
        ("source_mode", ("STAGE3_PACKAGE", "STORY_ONLY")),
        ("coverage", ("KEY_SCENES", "FULL_STORY")),
        ("timing_basis", ("ESTIMATED", "MEASURED", "UNAVAILABLE")),
    ):
        if plan.get(key) not in allowed:
            errors.append(f"{key} không hợp lệ")
    story: dict[str, Any] = {}
    try:
        story_raw = members.get("story.json") if members is not None else (
            (root / "story.json").read_bytes() if root else None
        )
        if story_raw is not None:
            story = read_json(story_raw)
    except (OSError, ValueError) as exc:
        errors.append(f"story.json không đọc được: {exc}")
    raw_script = story.get("script")
    script = raw_script if isinstance(raw_script, list) else []
    by_id: dict[str, Mapping[str, Any]] = {}
    if not script:
        errors.append("story.json.script phải là array không rỗng")
    for row in script:
        if (not isinstance(row, Mapping) or not isinstance(row.get("id"), str)
                or not isinstance(row.get("text"), str)):
            errors.append("story.json.script chứa dòng không hợp lệ")
            continue
        sid = row["id"]
        if sid in by_id:
            errors.append(f"story.json.script trùng id {sid}")
        by_id[sid] = row
    covered: dict[str, list[tuple[int, int]]] = {key: [] for key in by_id}
    rows: list[dict[str, Any]] = []
    duration = 0.0
    for index, clip in enumerate(clips, 1):
        if not isinstance(clip, Mapping) or clip.get("clip_id") != f"clip_{index:04d}":
            errors.append(f"Clip {index}: clip_id không liên tục")
            continue
        spans = clip.get("source_spans")
        parts: list[str] = []
        if not isinstance(spans, list) or not spans:
            errors.append(f"Clip {index}: source_spans rỗng")
            continue
        for span in spans:
            if not isinstance(span, Mapping) or set(span) != {"script_id", "start_char", "end_char"}:
                errors.append(f"Clip {index}: source span sai schema")
                continue
            sid = span.get("script_id")
            source = by_id.get(sid) if isinstance(sid, str) else None
            start, end = span.get("start_char"), span.get("end_char")
            text = source.get("text") if source is not None else None
            if (not isinstance(sid, str) or not isinstance(text, str)
                    or type(start) is not int or type(end) is not int or not (0 <= start < end <= len(text))):
                errors.append(f"Clip {index}: offset không hợp lệ")
                continue
            parts.append(text[start:end])
            covered[sid].append((start, end))
        if clip.get("narration") != " ".join(parts):
            errors.append(f"Clip {index}: narration không khớp exact spans")
        seconds = clip.get("estimated_seconds")
        if plan.get("timing_basis") == "UNAVAILABLE":
            if seconds is not None:
                errors.append(f"Clip {index}: estimated_seconds phải null")
        elif (not (type(seconds) is int or type(seconds) is float)
              or not math.isfinite(seconds) or seconds <= 0):
            errors.append(f"Clip {index}: estimated_seconds không hợp lệ")
        else:
            duration += seconds
        references = clip.get("reference_paths", [])
        if not isinstance(references, list):
            errors.append(f"Clip {index}: reference_paths phải là array")
            references = []
        for path in references:
            exists = False
            if isinstance(path, str) and safe_name(path):
                if members is not None:
                    exists = path in members
                elif root is not None:
                    target = (root / path).resolve()
                    exists = target.is_relative_to(root.resolve()) and target.is_file()
            if not exists:
                errors.append(f"Clip {index}: reference_path không tồn tại: {path}")
        rows.append({"Clip": clip.get("clip_id"), "Zone": "—", "Scene": "—", "Bắt đầu (s)": None,
                     "Kết thúc (s)": None, "Độ dài video (s)": seconds, "Tỷ lệ": clip.get("aspect_ratio")})
    if plan.get("coverage") == "FULL_STORY":
        for sid, row in by_id.items():
            cursor = 0
            for start, end in sorted(covered[sid]):
                if start != cursor:
                    errors.append(f"FULL_STORY không phủ exact {sid}")
                    break
                cursor = end
            if cursor != len(row["text"]):
                errors.append(f"FULL_STORY không phủ hết {sid}")
    return {"errors": errors, "checks": [], "clips": rows, "duration": duration,
            "needs_confirmation": len(clips) > 60, "continuity_status": "NOT_VERIFIED" if errors else "PASS",
            "speech_timing_status": "NOT_APPLICABLE", "speech_timing": []}


def validate_v5_plan(plan: Mapping[str, Any], *, members: Mapping[str, bytes]) -> dict[str, Any]:
    """Apply the closed v5 Stage-1 contract on top of legacy span validation."""
    result = validate_v4_plan(plan, root=None, members=members)
    errors = list(result["errors"])
    if set(plan) != V4_FIELDS:
        errors.append("video_prompts root không đúng closed schema")
    if plan.get("source_mode") != "STORY_ONLY":
        errors.append("V5 yêu cầu source_mode=STORY_ONLY")
    target = plan.get("target_model")
    if target is not None and (not isinstance(target, str) or not target.strip()):
        errors.append("target_model phải là string không rỗng hoặc null")
    limitations = plan.get("limitations")
    if (not isinstance(limitations, list) or not all(isinstance(item, str) and item.strip() for item in limitations)
            or len(limitations) != len(set(limitations))):
        errors.append("limitations phải là array string duy nhất")
    timing = plan.get("timing_config")
    if not isinstance(timing, Mapping) or set(timing) != TIMING_FIELDS:
        errors.append("timing_config không đúng closed schema")
    else:
        basis = plan.get("timing_basis")
        method, rate, evidence = timing.get("method_id"), timing.get("rate_per_minute"), timing.get("evidence_locator")
        if basis == "UNAVAILABLE" and (method != "NONE" or rate is not None or evidence is not None):
            errors.append("UNAVAILABLE yêu cầu timing_config NONE/null/null")
        elif basis == "MEASURED" and (method != "ALIGNED_SPAN_TIMING_V1" or rate is not None
                                      or not isinstance(evidence, str) or not evidence.strip()):
            errors.append("MEASURED yêu cầu timing evidence theo span")
        elif basis == "ESTIMATED" and (not isinstance(method, str) or not method.strip()
                                        or (rate is not None and (type(rate) not in {int, float}
                                                                  or not math.isfinite(rate) or rate <= 0))):
            errors.append("ESTIMATED yêu cầu method và rate hợp lệ")
    raw_clips = plan.get("clips")
    if isinstance(raw_clips, list):
        for index, clip in enumerate(raw_clips, 1):
            if not isinstance(clip, Mapping) or set(clip) != CLIP_FIELDS:
                errors.append(f"Clip {index}: không đúng closed schema")
                continue
            if clip.get("aspect_ratio") not in {"16:9", "9:16"}:
                errors.append(f"Clip {index}: aspect_ratio không hợp lệ")
            if not isinstance(clip.get("prompt"), str) or not clip["prompt"].strip():
                errors.append(f"Clip {index}: prompt phải là string không rỗng")
            if not isinstance(clip.get("audio_note"), str) or not isinstance(clip.get("transition"), str):
                errors.append(f"Clip {index}: audio_note/transition phải là string")
            if clip.get("reference_paths") != []:
                errors.append(f"Clip {index}: V5 Stage 1 yêu cầu reference_paths=[]")
    result["errors"] = list(dict.fromkeys(errors))
    result["continuity_status"] = "NOT_VERIFIED" if result["errors"] else "PASS"
    return result


__all__ = ["V4_FIELDS", "validate_v4_plan", "validate_v5_plan"]
