"""Strict reader and inspector for ChatGPT Audio Story packages v4.1.6.

The public data schema is 4.1.3 while the authoring prompt is 4.1.6. There is
deliberately no legacy adapter: a package is either current or rejected.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from PIL import Image, UnidentifiedImageError

from studio.artifact_validation import strict_json_bytes, validate_series_anchor_bytes
from studio.image_prompt_validation import validate_image_prompt_bytes
from studio.prompt_contract import (
    PromptContract,
    load_prompt_contract,
    prompt_contract_for_version,
)
from studio.story_schema import validate_story_document

WORKFLOW_FILES = {"workflow": "manifest.json", "image_prompts": "image_prompts.json", "visual_bible": "visual_plan.json", "video_prompts": "video_prompts.json"}
STAGES = ("STAGE1", "STAGE2", "STAGE3", "STAGE4")
PURPOSES: tuple[str, ...] = ()
MANIFEST_FIELDS = ("schema_version", "prompt_version", "stage", "status", "parent_package_sha256", "files")
FILE_FIELDS = ("path", "size_bytes", "sha256", "origin_stage")
VALIDATION_FIELDS: tuple[str, ...] = ()
# Delivery packages may contain a single high-resolution video larger than
# 128 MiB. Keep the per-member ceiling below the overall package ceiling so
# archive-bomb protection remains bounded while valid 4K media can be audited.
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 5 * 1024 * 1024
ZONE_BASENAMES = ("cover.png", "greeting.png", "opening.png", "introduction.png", "development.png", "climax.png", "falling.png", "ending.png", "farewell.png", "outro.png")
CHECK_FIELDS = {"id", "status", "method", "required", "target", "details"}
CHECK_STATUSES = {"PASS", "FAIL", "NOT_CHECKED", "NOT_APPLICABLE"}
CHECK_METHODS = {"CODE", "TOOL", "MODEL_REVIEW"}
V520_COMMON_GATES = {"JSON_PARSE", "SCHEMA_LINKS", "FILE_SET", "MANIFEST_MATCH", "CONTENT_SAFETY"}
V520_STAGE_GATES = {
    1: {"STORY_NOVELTY", "STORY_ORDER", "STORY_TIMING", "STORY_COMPLETENESS", "STORY_CRAFT",
        "SERIAL_CONTINUITY", "IMAGE_PROMPT_SCHEMA", "IMAGE_PROMPT_SOURCE_BINDING",
        "IMAGE_PROMPT_CHARACTER_LINKS", "IMAGE_PROMPT_T5_TOKENS",
        "IMAGE_REFERENCE_FILES", "IMAGE_REFERENCE_CONTENT",
        "VIDEO_SPANS", "VIDEO_FEASIBILITY", "VIDEO_TIMING"},
    2: {"INHERITED_BYTES", "VISUAL_PLAN", "IMAGE_FILES", "IMAGE_CONTENT"},
    3: {"INHERITED_BYTES", "VISUAL_PLAN", "IMAGE_FILES", "IMAGE_CONTENT", "ORIENTATION_PARITY"},
}
V520_GATE_METHODS = {
    "JSON_PARSE": {"CODE", "TOOL"}, "SCHEMA_LINKS": {"CODE", "TOOL"},
    "FILE_SET": {"CODE", "TOOL"}, "MANIFEST_MATCH": {"CODE", "TOOL"},
    "CONTENT_SAFETY": {"MODEL_REVIEW"}, "STORY_NOVELTY": {"MODEL_REVIEW"},
    "STORY_ORDER": {"CODE", "TOOL"}, "STORY_TIMING": {"CODE", "TOOL"},
    "STORY_COMPLETENESS": {"MODEL_REVIEW"}, "STORY_CRAFT": {"MODEL_REVIEW"},
    "SERIAL_CONTINUITY": {"CODE", "TOOL", "MODEL_REVIEW"},
    "IMAGE_PROMPT_SCHEMA": {"CODE", "TOOL"}, "IMAGE_PROMPT_SOURCE_BINDING": {"CODE", "TOOL"},
    "IMAGE_PROMPT_CHARACTER_LINKS": {"CODE", "TOOL"},
    "IMAGE_PROMPT_T5_TOKENS": {"TOOL"}, "IMAGE_REFERENCE_FILES": {"CODE", "TOOL"},
    "IMAGE_REFERENCE_CONTENT": {"MODEL_REVIEW"}, "VIDEO_SPANS": {"CODE", "TOOL"},
    "VIDEO_FEASIBILITY": {"MODEL_REVIEW"}, "VIDEO_TIMING": {"CODE", "TOOL"},
    "INHERITED_BYTES": {"CODE", "TOOL"}, "VISUAL_PLAN": {"CODE", "TOOL"},
    "IMAGE_FILES": {"CODE", "TOOL"}, "IMAGE_CONTENT": {"MODEL_REVIEW"},
    "ORIENTATION_PARITY": {"MODEL_REVIEW"},
}


def _required_stage_gates(stage: Any, contract: PromptContract) -> set[str]:
    """Return the gates required by the selected prompt revision.

    Prompt v5.2.2 revision r3 retired the T5-512 token gate while retaining
    the legacy check identifier for readers that still emit it.
    """
    required = V520_COMMON_GATES | V520_STAGE_GATES.get(stage, set())
    if contract.version >= (5, 2, 2):
        required = required - {"IMAGE_PROMPT_T5_TOKENS"}
    return required


def required_stage_gate_ids(stage: Any, prompt_version: str) -> set[str]:
    """Return the public, version-aware gate contract used by Studio diagnostics."""
    return _required_stage_gates(stage, prompt_contract_for_version(prompt_version))


def stage_gate_contract_diagnostics(report: Mapping[str, Any]) -> dict[str, Any]:
    """Compare declared checks with the gate contract without trusting their verdicts."""
    prompt_version = str(report.get("prompt_version") or "")
    required = required_stage_gate_ids(report.get("stage"), prompt_version)
    checks = report.get("checks")
    rows = checks if isinstance(checks, list) else []
    declared = {
        str(row.get("id")) for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }
    resolved = {
        str(row.get("id")) for row in rows
        if isinstance(row, Mapping) and row.get("required") is True
        and row.get("status") in {"PASS", "NOT_APPLICABLE"}
    }
    return {
        "required": sorted(required),
        "declared": sorted(declared),
        "missing": sorted(required - declared),
        "unexpected": sorted(declared - required),
        "resolved_required": sorted(required & resolved),
    }


def _v520_not_applicable(identifier: str, members: Mapping[str, bytes]) -> bool:
    """Return whether payload facts make a required v5.2 gate inapplicable."""
    if identifier == "SERIAL_CONTINUITY":
        story = read_json(members.get("story.json", b"{}"))
        return isinstance(story.get("meta"), Mapping) and story["meta"].get("profile") != "SERIAL_DETECTIVE"
    if identifier == "STORY_TIMING":
        story = read_json(members.get("story.json", b"{}"))
        return isinstance(story.get("meta"), Mapping) and story["meta"].get("language") not in {"vi", "en"}
    if identifier in {"IMAGE_REFERENCE_FILES", "IMAGE_REFERENCE_CONTENT"}:
        prompts = read_json(members.get("image_prompts.json", b"{}"))
        locks = prompts.get("character_locks")
        return isinstance(locks, list) and bool(locks) and all(
            isinstance(row, Mapping) and row.get("planned_reference_path") is None for row in locks
        )
    return False


def validate_visual_plan(document: Mapping[str, Any]) -> list[str]:
    """Validate the closed v5.2 visual-plan schema and reference state machine."""
    errors: list[str] = []
    if set(document) != {"schema_version", "image_mode", "reference_mode", "targets", "characters", "assets"}:
        errors.append("visual_plan root không đúng closed schema")
    if document.get("schema_version") != "4.1.3":
        errors.append("visual_plan.schema_version phải là 4.1.3")
    mode = document.get("reference_mode")
    if mode not in {"IMAGE_REFERENCE", "DESCRIPTION_ONLY"}:
        errors.append("visual_plan.reference_mode không hợp lệ")
    targets = document.get("targets")
    target_fields = {"size_policy", "preferred_aspect_ratio", "width", "height"}
    if not isinstance(targets, Mapping) or set(targets) != {"landscape", "portrait"}:
        errors.append("visual_plan.targets không đúng closed schema")
    else:
        for aspect, ratio in (("landscape", "16:9"), ("portrait", "9:16")):
            target = targets.get(aspect)
            if not isinstance(target, Mapping) or set(target) != target_fields:
                errors.append(f"visual_plan.targets.{aspect} không đúng closed schema")
                continue
            policy, width, height = target.get("size_policy"), target.get("width"), target.get("height")
            if target.get("preferred_aspect_ratio") != ratio or policy not in {"EXACT", "MODEL_DEFAULT"}:
                errors.append(f"visual_plan.targets.{aspect} không hợp lệ")
            if policy == "EXACT" and not (type(width) is int and width > 0 and type(height) is int and height > 0):
                errors.append(f"visual_plan.targets.{aspect} EXACT thiếu kích thước")
            if policy == "MODEL_DEFAULT" and (width is not None or height is not None):
                errors.append(f"visual_plan.targets.{aspect} MODEL_DEFAULT phải có width/height null")
    characters = document.get("characters")
    character_fields = {"character_id", "planned_reference_path", "reference_path", "reference_status", "description_lock"}
    if not isinstance(characters, list):
        errors.append("visual_plan.characters phải là array")
    else:
        ids: list[str] = []
        for row in characters:
            if not isinstance(row, Mapping) or set(row) != character_fields:
                errors.append("visual_plan.characters[] không đúng closed schema")
                continue
            identifier, planned, path = row.get("character_id"), row.get("planned_reference_path"), row.get("reference_path")
            if not isinstance(identifier, str) or not identifier or not isinstance(row.get("description_lock"), str) or not row["description_lock"].strip():
                errors.append("visual_plan.characters[] thiếu character_id/description_lock")
                continue
            ids.append(identifier)
            status = row.get("reference_status")
            if mode == "DESCRIPTION_ONLY" and (planned is not None or path is not None or status != "NOT_APPLICABLE"):
                errors.append(f"{identifier}: trạng thái reference không khớp DESCRIPTION_ONLY")
            if mode == "IMAGE_REFERENCE":
                expected = f"characters/{identifier}.png"
                if planned != expected or status not in {"PENDING", "READY", "FAILED"}:
                    errors.append(f"{identifier}: trạng thái reference không khớp IMAGE_REFERENCE")
                elif (status == "READY" and path != planned) or (status != "READY" and path is not None):
                    errors.append(f"{identifier}: reference_path không khớp reference_status")
        if len(ids) != len(set(ids)):
            errors.append("visual_plan.characters có character_id trùng")
    assets = document.get("assets")
    asset_fields = {"basename", "role", "source_script_ids", "character_ids", "brief", "landscape_prompt", "portrait_prompt"}
    if not isinstance(assets, list) or not assets:
        errors.append("visual_plan.assets phải là array không rỗng")
    elif any(not isinstance(row, Mapping) or set(row) != asset_fields for row in assets):
        errors.append("visual_plan.assets[] không đúng closed schema")
    try:
        active_image_basenames(document)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def read_json(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON vượt giới hạn 5 MiB")
    return dict(strict_json_bytes(raw))


def safe_name(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    return (not path.is_absolute() and path.as_posix() == name
            and all(part not in {"", ".", ".."} and not part.endswith((".", " ")) for part in path.parts)
            and unicodedata.normalize("NFC", name) == name)


def read_archive(source: Path | bytes) -> dict[str, bytes]:
    size = source.stat().st_size if isinstance(source, Path) else len(source)
    if size > MAX_PACKAGE_BYTES:
        raise ValueError("ZIP vượt giới hạn 512 MiB")
    result: dict[str, bytes] = {}
    folded: set[str] = set()
    with zipfile.ZipFile(source if isinstance(source, Path) else BytesIO(source)) as archive:
        infos = archive.infolist()
        if len(infos) > 1024 or sum(item.file_size for item in infos) > MAX_PACKAGE_BYTES:
            raise ValueError("ZIP vượt giới hạn số file/dung lượng giải nén")
        for item in infos:
            if item.is_dir():
                continue
            mode = item.external_attr >> 16
            key = unicodedata.normalize("NFC", item.filename).casefold()
            file_type = stat.S_IFMT(mode)
            if (not safe_name(item.filename) or key in folded or stat.S_ISLNK(mode)
                    or file_type not in {0, stat.S_IFREG} or item.file_size > MAX_MEMBER_BYTES):
                raise ValueError(f"Thành viên ZIP không an toàn: {item.filename}")
            folded.add(key)
            result[item.filename] = archive.read(item)
        bad = archive.testzip()
        if bad:
            raise ValueError(f"CRC lỗi: {bad}")
    return result


def active_image_basenames(visual_plan: Mapping[str, Any], contract: PromptContract | None = None) -> tuple[str, ...]:
    mode, assets = visual_plan.get("image_mode"), visual_plan.get("assets")
    if mode not in {"ZONE", "SCENE"} or not isinstance(assets, list) or not assets:
        raise ValueError("visual_plan.image_mode/assets không hợp lệ")
    names: list[str] = []
    for row in assets:
        name = row.get("basename") if isinstance(row, Mapping) else None
        if not isinstance(name, str) or not safe_name(name) or "/" in name or not name.endswith(".png"):
            raise ValueError("visual_plan.assets[].basename không hợp lệ")
        names.append(name)
    if len(names) != len(set(name.casefold() for name in names)):
        raise ValueError("visual_plan có basename trùng")
    if mode == "ZONE" and tuple(names) != ZONE_BASENAMES:
        raise ValueError("Bộ basename ZONE không đúng v4.1.6")
    if mode == "SCENE":
        middle = names[2:-2]
        if names[:2] != ["cover.png", "greeting.png"] or names[-2:] != ["farewell.png", "outro.png"]:
            raise ValueError("Bộ basename SCENE thiếu đầu/cuối chuẩn")
        if middle != [f"scene_{index:04d}.png" for index in range(1, len(middle) + 1)]:
            raise ValueError("Tên ảnh SCENE không liên tục")
    return tuple(names)


def _stage_label(stage: Any, contract: PromptContract) -> str | None:
    label = f"STAGE{stage}" if type(stage) is int else None
    return label if label in contract.workflow_package_stages else None


def _expected_payload(members: Mapping[str, bytes], stage: int, contract: PromptContract | None = None) -> set[str]:
    contract = contract or load_prompt_contract()
    expected = {"story.json", "validation_report.json"}
    story = read_json(members.get("story.json", b"{}"))
    if isinstance(story.get("meta"), Mapping) and story["meta"].get("profile") == "SERIAL_DETECTIVE":
        expected.add("series_anchor.json")
    is_v5 = contract.version >= (5, 0, 0)
    if is_v5:
        expected.update({"image_prompts.json", "video_prompts.json"})
        if contract.version >= (5, 2, 0):
            image_prompts = read_json(members.get("image_prompts.json", b"{}"))
            for row in image_prompts.get("character_locks", []):
                if isinstance(row, Mapping) and isinstance(row.get("planned_reference_path"), str):
                    expected.add(row["planned_reference_path"])
    story_only = False
    if not is_v5 and stage == 4 and "video_prompts.json" in members:
        story_only = read_json(members["video_prompts.json"]).get("source_mode") == "STORY_ONLY"
    if stage >= 2 and not story_only:
        expected.update({"visual_plan.json", "visual_bible.txt"})
        plan = read_json(members.get("visual_plan.json", b"{}"))
        for name in active_image_basenames(plan):
            expected.add(f"landscape/{name}")
            if stage >= 3:
                expected.add(f"portrait/{name}")
        for row in plan.get("characters", []):
            if isinstance(row, Mapping) and isinstance(row.get("reference_path"), str):
                expected.add(row["reference_path"])
    if not is_v5 and stage == 4:
        expected.add("video_prompts.json")
    return expected


def package_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stage_gate_assessment(members: Mapping[str, bytes], contract: PromptContract) -> tuple[str, str]:
    """Resolve required report gates, replacing the legacy external anchor check locally."""
    try:
        report = read_json(members["validation_report.json"])
    except (KeyError, ValueError):
        return "FAIL", "Không đọc được validation_report.json để tổng hợp gate."
    checks = report.get("checks")
    if not isinstance(checks, list):
        return "FAIL", "validation_report.checks phải là array."
    unresolved: list[str] = []
    failed: list[str] = []
    seen: set[str] = set()
    resolved_anchor = False
    if "series_anchor.json" in members:
        anchor_result = validate_series_anchor_bytes(members["series_anchor.json"], contract)
        resolved_anchor = anchor_result.status == "PASS"
        if not resolved_anchor:
            failed.extend(f"ANCHOR_NESTED_SCHEMA: {message}" for message in anchor_result.errors)
    for row in checks:
        if not isinstance(row, Mapping):
            failed.append("CHECK_SCHEMA: record không phải object")
            continue
        identifier = str(row.get("id") or "UNKNOWN_GATE")
        if (set(row) != CHECK_FIELDS or identifier in seen
                or row.get("status") not in CHECK_STATUSES or row.get("method") not in CHECK_METHODS
                or type(row.get("required")) is not bool
                or not isinstance(row.get("target"), str) or not row["target"].strip()
                or not isinstance(row.get("details"), str) or not row["details"].strip()):
            failed.append(f"CHECK_SCHEMA: {identifier}")
            continue
        if contract.version >= (5, 2, 0) and identifier in V520_GATE_METHODS:
            optional_t5 = (
                contract.version >= (5, 2, 2)
                and identifier == "IMAGE_PROMPT_T5_TOKENS"
            )
            if ((row.get("required") is not True and not optional_t5)
                    or row.get("method") not in V520_GATE_METHODS[identifier]):
                failed.append(f"CHECK_POLICY: {identifier}")
                continue
        seen.add(identifier)
        if row.get("required") is not True:
            continue
        status = str(row.get("status") or "NOT_CHECKED")
        if identifier == "ANCHOR_EXTERNAL_NESTED_SCHEMA" and resolved_anchor:
            continue
        if status == "FAIL":
            failed.append(identifier)
        elif status == "NOT_APPLICABLE" and contract.version >= (5, 2, 0) and not _v520_not_applicable(identifier, members):
            failed.append(f"NOT_APPLICABLE: {identifier}")
        elif status not in {"PASS", "NOT_APPLICABLE"}:
            unresolved.append(identifier)
    if contract.version >= (5, 2, 0):
        manifest = read_json(members.get("manifest.json", b"{}"))
        stage = manifest.get("stage")
        required = _required_stage_gates(stage, contract)
        missing = sorted(required - seen)
        if missing:
            unresolved.extend(f"MISSING:{identifier}" for identifier in missing)
    if failed:
        visible = failed[:8]
        suffix = f"; và {len(failed) - len(visible)} lỗi khác" if len(failed) > len(visible) else ""
        return "FAIL", "Gate bắt buộc không đạt: " + "; ".join(visible) + suffix
    if unresolved:
        return "NOT_VERIFIED", "Gate bắt buộc chưa có bằng chứng: " + ", ".join(unresolved)
    return "PASS", "Mọi gate bắt buộc đã đạt bằng chứng deterministic hoặc report hợp lệ."


def aggregate_package_status(integrity_status: str, gate_status: str, completion_status: str) -> tuple[str, str]:
    """Return user-facing aggregate and publish status without conflating its three inputs."""
    if integrity_status == "FAIL" or gate_status == "FAIL":
        return "FAIL", "FAIL"
    if integrity_status != "PASS" or gate_status != "PASS":
        return "NOT_VERIFIED", "FAIL"
    if completion_status != "COMPLETE":
        return "PARTIAL", "FAIL"
    return "PASS", "PASS"


def inspect_members(members: Mapping[str, bytes], *, archive: bool = False, parent: Mapping[str, bytes] | None = None,
                    contract: PromptContract | None = None, overridden: bool = False) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    def check(name: str, ok: bool, good: str, bad: str) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detector_class": "DETERMINISTIC", "detail": good if ok else bad})
    if "manifest.json" not in members:
        check("manifest_schema", False, "", "Thiếu manifest.json v4.1.6")
        return {"status": "FAIL", "overall_status": "FAIL", "integrity_status": "FAIL",
                "stage_gate_status": "NOT_VERIFIED", "package_completion_status": "UNKNOWN",
                "publish_status": "FAIL", "compatibility": "UNSUPPORTED", "stage": None,
                "checks": checks, "files": [], "manifest": {}, "actual_package_digest_sha256": None}
    try:
        manifest = read_json(members["manifest.json"])
    except ValueError as exc:
        check("manifest_schema", False, "", f"manifest.json không hợp lệ: {exc}")
        return {"status": "FAIL", "overall_status": "FAIL", "integrity_status": "FAIL",
                "stage_gate_status": "NOT_VERIFIED", "package_completion_status": "UNKNOWN",
                "publish_status": "FAIL", "compatibility": "UNSUPPORTED", "stage": None,
                "checks": checks, "files": [], "manifest": {}, "actual_package_digest_sha256": None}
    if contract is None:
        try:
            contract = prompt_contract_for_version(str(manifest.get("prompt_version") or ""))
        except (OSError, ValueError) as exc:
            check("prompt_contract", False, "", str(exc))
            return {"status": "FAIL", "overall_status": "FAIL", "integrity_status": "FAIL",
                    "stage_gate_status": "NOT_VERIFIED", "package_completion_status": "UNKNOWN",
                    "publish_status": "FAIL", "compatibility": "UNSUPPORTED", "stage": None,
                    "checks": checks, "files": [], "manifest": manifest, "actual_package_digest_sha256": None}
    stage, rows = manifest.get("stage"), manifest.get("files")
    stage_label = _stage_label(stage, contract)
    digest_pattern = re.compile(r"[0-9a-f]{64}")
    parent_digest = manifest.get("parent_package_sha256")
    manifest_schema = contract.workflow_manifest_schema_version or "4.1.3"
    schema_ok = (set(manifest) == set(MANIFEST_FIELDS) and manifest.get("schema_version") == manifest_schema
                 and manifest.get("prompt_version") == contract.version_label and stage_label is not None
                 and manifest.get("status") in ("COMPLETE", "PARTIAL", "BLOCKED")
                 and (parent_digest is None or isinstance(parent_digest, str) and digest_pattern.fullmatch(parent_digest) is not None))
    check("manifest_schema", schema_ok, f"Manifest v{contract.version_label} / schema {manifest_schema} hợp lệ.",
          f"Manifest không đúng schema của prompt v{contract.version_label}.")
    row_ok, indexed = isinstance(rows, list), {}
    if isinstance(rows, list):
        paths = []
        for row in rows:
            valid = (isinstance(row, Mapping) and set(row) == set(FILE_FIELDS) and isinstance(row.get("path"), str)
                     and safe_name(row["path"]) and type(row.get("size_bytes")) is int and row["size_bytes"] >= 0
                     and (row.get("sha256") is None or (isinstance(row.get("sha256"), str)
                          and digest_pattern.fullmatch(row["sha256"])))
                     and type(row.get("origin_stage")) is int and 1 <= row["origin_stage"] <= len(contract.workflow_package_stages))
            if not valid:
                row_ok = False
                break
            paths.append(row["path"])
            indexed[row["path"]] = row
        row_ok = row_ok and paths == sorted(paths) and len(paths) == len(set(p.casefold() for p in paths))
    check("manifest_files", row_ok, "Danh sách manifest hợp lệ.", "manifest.files không hợp lệ.")
    actual_payload, listed = set(members) - {"manifest.json"}, set(indexed)
    file_set_ok = row_ok and actual_payload == listed
    file_set_error: str | None = None
    if type(stage) is int and stage_label:
        try:
            expected_payload = _expected_payload(members, stage, contract)
            required_payload = {"story.json", "validation_report.json"}
            if contract.version >= (5, 0, 0):
                required_payload.update({"image_prompts.json", "video_prompts.json"})
            elif stage == 4:
                required_payload.add("video_prompts.json")
            if manifest.get("status") == "COMPLETE":
                file_set_ok = file_set_ok and actual_payload == expected_payload
            else:
                file_set_ok = file_set_ok and required_payload <= actual_payload <= expected_payload
        except (ValueError, KeyError, TypeError) as exc:
            file_set_ok = False
            file_set_error = str(exc)
    file_set_bad = (
        f"Không thể xác định file set do visual plan không hợp lệ: {file_set_error}"
        if file_set_error else f"File set không đúng stage/schema prompt v{contract.version_label}."
    )
    check("file_set", file_set_ok, f"Exact file set Stage {stage} hợp lệ.", file_set_bad)
    digest_ok = row_ok
    digest_mismatches: list[str] = []
    for path, row in indexed.items():
        raw = members.get(path)
        reasons = []
        if raw is None:
            reasons.append("thiếu file")
        elif len(raw) != row["size_bytes"]:
            reasons.append("sai kích thước")
        if raw is not None and row.get("sha256") is not None and hashlib.sha256(raw).hexdigest() != row["sha256"]:
            reasons.append("sai SHA-256")
        if reasons:
            digest_mismatches.append(f"{path} ({', '.join(reasons)})")
            digest_ok = False
    visible_mismatches = digest_mismatches[:5]
    mismatch_suffix = (
        f"; và {len(digest_mismatches) - len(visible_mismatches)} file khác"
        if len(digest_mismatches) > len(visible_mismatches) else ""
    )
    digest_error = (
        "Payload không khớp manifest: " + "; ".join(visible_mismatches) + mismatch_suffix + "."
        if visible_mismatches else "Size/hash payload không khớp manifest."
    )
    check("file_digest", digest_ok, "Size/hash mọi payload khớp manifest.", digest_error)
    inherited_ok = True
    inherited_error = ""
    if parent is not None:
        try:
            parent_manifest = read_json(parent["manifest.json"])
            parent_stage = parent_manifest.get("stage")
            inherited_names = {"story.json"}
            if contract.version >= (5, 0, 0):
                inherited_names.update({"image_prompts.json", "video_prompts.json"})
            if contract.version >= (5, 2, 0) and "image_prompts.json" in parent:
                image_prompts = read_json(parent["image_prompts.json"])
                inherited_names.update(
                    row["planned_reference_path"]
                    for row in image_prompts.get("character_locks", [])
                    if isinstance(row, Mapping) and isinstance(row.get("planned_reference_path"), str)
                )
            if "series_anchor.json" in parent:
                inherited_names.add("series_anchor.json")
            inherited_ok = bool(parent_manifest.get("prompt_version") == contract.version_label
                                and type(parent_stage) is int and type(stage) is int
                                and (stage == parent_stage or stage == parent_stage + 1)
                                and all(name in members and members[name] == parent[name] for name in inherited_names))
            if not inherited_ok:
                inherited_error = "Parent stage/version hoặc exact bytes payload kế thừa không khớp."
        except (KeyError, TypeError, ValueError) as exc:
            inherited_ok = False
            inherited_error = str(exc)
    check("inherited_bytes", inherited_ok, "Payload canonical kế thừa giữ exact bytes.",
          inherited_error or "Payload kế thừa không khớp parent.")
    json_ok = True
    for path, raw in members.items():
        if path.endswith(".json"):
            try:
                document = read_json(raw)
                expected_schema = (
                    manifest_schema if path in {"manifest.json", "validation_report.json"}
                    else None if path == "image_prompts.json" else "4.1.3"
                )
                json_ok = json_ok and (expected_schema is None or document.get("schema_version") == expected_schema)
            except ValueError:
                json_ok = False
    check("strict_json", json_ok, "Mọi JSON parse strict và dùng schema artifact tương ứng.", "JSON lỗi hoặc schema_version không đúng artifact.")
    try:
        story_errors = (
            validate_story_document(read_json(members["story.json"]))
            if contract.version >= (5, 2, 0) else []
        )
    except (KeyError, ValueError) as exc:
        story_errors = [str(exc)]
    check("story_schema", not story_errors, "story.json đạt closed schema và liên kết nội bộ.",
          "; ".join(story_errors[:5]) or "story.json không hợp lệ.")
    report_ok = False
    try:
        report = read_json(members["validation_report.json"])
        report_ok = (
            set(report) == {"schema_version", "prompt_version", "stage", "status", "input_sources",
                            "checks", "limitations", "remaining_work", "archive_validation"}
            and report.get("schema_version") == contract.story_validation_schema_version
            and report.get("prompt_version") == contract.version_label
            and report.get("stage") == stage
            and report.get("status") == manifest.get("status")
            and isinstance(report.get("checks"), list)
            and (contract.version < (5, 2, 0) or (
                isinstance(report.get("input_sources"), list)
                and all(isinstance(item, str) and item.strip() for item in report.get("input_sources", []))
                and isinstance(report.get("limitations"), list)
                and all(isinstance(item, str) and item.strip() for item in report.get("limitations", []))
                and isinstance(report.get("remaining_work"), list)
                and all(isinstance(item, str) and item.strip() for item in report.get("remaining_work", []))
                and isinstance(report.get("archive_validation"), Mapping)
                and set(report.get("archive_validation", {})) == {"status", "details"}
                and report["archive_validation"].get("status") in CHECK_STATUSES
                and (not archive or report["archive_validation"].get("status") == "NOT_CHECKED")
                and isinstance(report["archive_validation"].get("details"), str)
                and bool(report["archive_validation"]["details"].strip())
            ))
        )
    except (KeyError, ValueError):
        report_ok = False
    check("validation_report", report_ok, "Report khớp schema, prompt, stage và trạng thái manifest.",
          f"validation_report.json không khớp manifest hoặc closed schema v{contract.version_label}.")

    if contract.image_prompt_version:
        image_prompt_errors = validate_image_prompt_bytes(
            members.get("image_prompts.json", b""), members.get("story.json", b""),
            expected_prompt_version=contract.version_label,
        )
        check("image_prompts", not image_prompt_errors, "image_prompts.json khớp story và closed schema.",
              "; ".join(image_prompt_errors[:4]) or "Thiếu image_prompts.json.")
        try:
            from studio.video_prompt_v4 import validate_v4_plan, validate_v5_plan

            video_plan = read_json(members["video_prompts.json"])
            video_result = (
                validate_v5_plan(video_plan, members=members)
                if contract.version >= (5, 2, 0)
                else validate_v4_plan(video_plan, root=None, members=members)
            )
            video_errors = list(video_result.get("errors") or [])
            if contract.version < (5, 2, 0):
                if video_plan.get("source_mode") != "STORY_ONLY" or any(
                    not isinstance(clip, Mapping) or clip.get("reference_paths") != []
                    for clip in video_plan.get("clips", [])
                ):
                    video_errors.append("V5 yêu cầu STORY_ONLY và reference_paths rỗng")
        except (KeyError, TypeError, ValueError) as exc:
            video_errors = [str(exc)]
        check("video_prompts", not video_errors, "video_prompts.json STORY_ONLY khớp story/spans.",
              "; ".join(video_errors[:4]) or "Thiếu video_prompts.json.")
        if type(stage) is int and stage >= 2 and "visual_plan.json" in members:
            try:
                image_plan = read_json(members["image_prompts.json"])
                visual_plan = read_json(members["visual_plan.json"])
                visual_errors = validate_visual_plan(visual_plan) if contract.version >= (5, 2, 0) else []
                if visual_errors:
                    raise ValueError("; ".join(visual_errors[:4]))
                image_assets = image_plan.get("assets")
                visual_assets = visual_plan.get("assets")
                if not isinstance(image_assets, list) or not isinstance(visual_assets, list):
                    raise ValueError("assets phải là array")
                prompt_rows = [
                    (row.get("basename"), row.get("role"), row.get("source_script_ids"),
                     row.get("character_ids"), row.get("brief"), row.get("landscape_prompt"),
                     row.get("portrait_prompt"))
                    for row in image_assets if isinstance(row, Mapping)
                ]
                visual_rows = [
                    (row.get("basename"), row.get("role"), row.get("source_script_ids"),
                     row.get("character_ids"), row.get("brief"), row.get("landscape_prompt"),
                     row.get("portrait_prompt"))
                    for row in visual_assets if isinstance(row, Mapping)
                ]
                plan_binding_ok = len(prompt_rows) == len(image_assets) == len(visual_rows) and prompt_rows == visual_rows
                if contract.version >= (5, 2, 0):
                    prompt_locks = {
                        row.get("character_id"): row.get("planned_reference_path")
                        for row in image_plan.get("character_locks", []) if isinstance(row, Mapping)
                    }
                    visual_locks = {
                        row.get("character_id"): row.get("reference_path")
                        for row in visual_plan.get("characters", []) if isinstance(row, Mapping)
                    }
                    prompt_visible = {
                        character_id for row in image_assets if isinstance(row, Mapping)
                        for character_id in row.get("character_ids", []) if isinstance(character_id, str)
                    }
                    visual_visible = {
                        character_id for row in visual_assets if isinstance(row, Mapping)
                        for character_id in row.get("character_ids", []) if isinstance(character_id, str)
                    }
                    plan_binding_ok = (
                        plan_binding_ok
                        and prompt_visible == visual_visible == set(visual_locks)
                        and prompt_visible <= set(prompt_locks)
                        and all(visual_locks.get(character_id) == prompt_locks.get(character_id)
                                for character_id in prompt_visible)
                    )
            except (KeyError, TypeError, ValueError) as exc:
                plan_binding_ok = False
                plan_binding_error = str(exc)
            else:
                plan_binding_error = ""
            check("image_prompt_visual_binding", plan_binding_ok,
                  "visual_plan ánh xạ một-một image_prompts assets.",
                  plan_binding_error or "visual_plan không ánh xạ exact image_prompts assets.")

    image_ok = True
    image_error: str | None = None
    if type(stage) is int and stage_label and (
        stage >= 2 and "visual_plan.json" in members
        or stage == 1 and contract.version >= (5, 2, 0) and "image_prompts.json" in members
    ):
        try:
            if stage == 1:
                image_prompts = read_json(members["image_prompts.json"])
                targets: Mapping[str, Any] = {}
                image_paths = [
                    row["planned_reference_path"] for row in image_prompts.get("character_locks", [])
                    if isinstance(row, Mapping) and isinstance(row.get("planned_reference_path"), str)
                ]
            else:
                plan = read_json(members["visual_plan.json"])
                targets = plan["targets"]
                aspects = ("landscape",) if stage == 2 else ("landscape", "portrait")
                image_names = active_image_basenames(plan)
                reference_names = [
                    row["reference_path"] for row in plan.get("characters", [])
                    if isinstance(row, Mapping) and isinstance(row.get("reference_path"), str)
                ]
                image_paths = [*(f"{aspect}/{name}" for aspect in aspects for name in image_names), *reference_names]
            for path in image_paths:
                raw = members.get(path)
                if raw is None:
                    image_ok = image_ok and manifest.get("status") != "COMPLETE"
                    continue
                with Image.open(BytesIO(raw)) as image:
                    image.verify()
                with Image.open(BytesIO(raw)) as image:
                    width, height = image.size
                    image_ok = image_ok and image.format == "PNG" and image.mode in {"RGB", "RGBA"} and not getattr(image, "is_animated", False)
                    if path.startswith("landscape/"):
                        image_ok = image_ok and width > height
                    elif path.startswith("portrait/"):
                        image_ok = image_ok and height > width
                    if path.startswith(("landscape/", "portrait/")):
                        aspect = path.split("/", 1)[0]
                        if not isinstance(targets, Mapping):
                            raise ValueError("visual_plan.targets phải là object")
                        target = targets.get(aspect, {})
                        if not isinstance(target, Mapping):
                            raise ValueError("visual_plan.targets phải chứa object theo tỷ lệ")
                        if target.get("size_policy") == "EXACT":
                            image_ok = image_ok and (width, height) == (target.get("width"), target.get("height"))
        except (KeyError, TypeError, ValueError, UnidentifiedImageError, OSError) as exc:
            image_ok = False
            image_error = str(exc)
    image_bad = (
        f"Không thể kiểm tra ảnh do visual plan hoặc tệp ảnh không hợp lệ: {image_error}"
        if image_error else "Ảnh không phải PNG hợp lệ hoặc sai orientation/size policy."
    )
    check("image_files", image_ok, "PNG giải mã được và đạt orientation/size policy.",
          image_bad)
    success = all(row["status"] == "PASS" for row in checks)
    payload_rows = [dict(indexed[path]) for path in sorted(indexed)] if row_ok else []
    integrity_status = "PASS" if success else "FAIL"
    completion_status = str(manifest.get("status") or "UNKNOWN")
    stage_gate_status, gate_detail = _stage_gate_assessment(members, contract)
    checks.append({"check": "stage_gates", "status": stage_gate_status,
                   "detector_class": "DETERMINISTIC", "detail": gate_detail})
    overall_status, publish_status = aggregate_package_status(
        integrity_status, stage_gate_status, completion_status
    )
    return {"status": integrity_status, "overall_status": overall_status,
            "integrity_status": integrity_status, "stage_gate_status": stage_gate_status,
            "package_completion_status": completion_status, "publish_status": publish_status,
            "compatibility": "NATIVE_CURRENT" if schema_ok else "UNSUPPORTED", "stage": stage_label,
            "package_stage": stage_label, "checks": checks, "manifest": manifest, "files": payload_rows,
            "actual_package_digest_sha256": package_digest(payload_rows) if row_ok else None,
            "overridden": overridden, "archive": archive}


def inspect_directory(root: Path, *, overridden: bool = False, parent: Mapping[str, bytes] | None = None,
                      contract: PromptContract | None = None) -> dict[str, Any]:
    try:
        manifest = read_json((root / "manifest.json").read_bytes())
        rows = manifest.get("files")
        if not isinstance(rows, list):
            raise ValueError("manifest.files phải là array")
        names = {"manifest.json", *(row["path"] for row in rows if isinstance(row, Mapping) and isinstance(row.get("path"), str))}
        resolved_root = root.resolve()
        if any(not safe_name(name) or not (root / name).resolve().is_relative_to(resolved_root) for name in names):
            raise ValueError("Đường dẫn payload không an toàn")
        members = {name: (root / Path(name)).read_bytes() for name in names}
        return inspect_members(members, parent=parent, contract=contract, overridden=overridden)
    except (OSError, ValueError, KeyError) as exc:
        result = inspect_members({}, contract=contract)
        result["checks"].append({"check": "directory", "status": "FAIL", "detector_class": "DETERMINISTIC", "detail": str(exc)})
        return result


__all__ = ["FILE_FIELDS", "MANIFEST_FIELDS", "PURPOSES", "STAGES", "VALIDATION_FIELDS", "WORKFLOW_FILES", "active_image_basenames", "aggregate_package_status", "inspect_directory", "inspect_members", "load_prompt_contract", "package_digest", "read_archive", "read_json", "required_stage_gate_ids", "safe_name", "stage_gate_contract_diagnostics"]
