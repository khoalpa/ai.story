"""Fail-closed migration of extracted workflow packages to the current contract."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.prompt_contract import CURRENT_PROMPT_VERSION, prompt_contract_for_version
from studio.workflow_builder import build_workflow_package, publish_package_atomic
from studio.workflow_package import (
    V520_COMMON_GATES,
    V520_GATE_METHODS,
    V520_STAGE_GATES,
    inspect_directory,
    read_archive,
    read_json,
    safe_name,
)

TARGET_VERSION = ".".join(map(str, CURRENT_PROMPT_VERSION))
SUPPORTED_SOURCE_VERSIONS = ("4.1.6", "4.2.0", "5.0.0", "5.1.0", "5.2.0", TARGET_VERSION)
MIGRATION_VERSION = "1.0"


@dataclass(frozen=True)
class MigrationResult:
    status: str
    source_version: str
    target_version: str
    stage: int
    archive_name: str
    archive_bytes: bytes
    members: Mapping[str, bytes]
    report: Mapping[str, Any]
    inspection: Mapping[str, Any]


@dataclass(frozen=True)
class LineageRebuildResult:
    archives: Mapping[str, bytes]
    final_members: Mapping[str, bytes]
    inspections: Mapping[int, Mapping[str, Any]]
    report: Mapping[str, Any]


def _json_bytes(value: Any) -> bytes:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return unicodedata.normalize("NFC", text).encode("utf-8")


def _directory_members(root: Path) -> dict[str, bytes]:
    manifest = read_json((root / "manifest.json").read_bytes())
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("manifest.files phải là array")
    names = ["manifest.json"]
    for row in rows:
        name = row.get("path") if isinstance(row, Mapping) else None
        if not isinstance(name, str) or not safe_name(name):
            raise ValueError("manifest chứa đường dẫn payload không an toàn")
        names.append(name)
    resolved = root.resolve()
    members: dict[str, bytes] = {}
    for name in names:
        path = root / Path(name)
        if not path.resolve().is_relative_to(resolved) or path.is_symlink() or not path.is_file():
            raise ValueError(f"Payload không an toàn hoặc bị thiếu: {name}")
        members[name] = path.read_bytes()
    return members


def _source_identity(members: Mapping[str, bytes]) -> tuple[str, int, int]:
    manifest = read_json(members.get("manifest.json", b"{}"))
    version, stage = manifest.get("prompt_version"), manifest.get("stage")
    if version not in SUPPORTED_SOURCE_VERSIONS:
        supported = ", ".join(SUPPORTED_SOURCE_VERSIONS)
        raise ValueError(f"UNSUPPORTED_SOURCE: chỉ hỗ trợ migration trực tiếp từ {supported}")
    if isinstance(version, str) and version.startswith("4."):
        if stage != 4:
            raise ValueError("UNSUPPORTED_SOURCE: gói v4 phải là Stage 4 đầy đủ để có đủ artifact v5.2")
        return version, stage, 3
    if type(stage) is not int or stage not in {1, 2, 3}:
        raise ValueError("UNSUPPORTED_SOURCE: stage nguồn phải là 1, 2 hoặc 3")
    return version, stage, stage


def _migration_checks(stage: int) -> list[dict[str, Any]]:
    identifiers = sorted(V520_COMMON_GATES | V520_STAGE_GATES.get(stage, set()))
    return [{
        "id": identifier,
        "status": "NOT_CHECKED",
        "method": sorted(V520_GATE_METHODS[identifier])[0],
        "required": True,
        "target": "package",
        "details": "Cần kiểm định lại sau migration; không kế thừa PASS từ phiên bản nguồn.",
    } for identifier in identifiers]


def _image_prompts_from_v4(files: Mapping[str, bytes]) -> dict[str, Any]:
    plan = read_json(files["visual_plan.json"])
    story = read_json(files["story.json"])
    script_ids = [row.get("id") for row in story.get("script", []) if isinstance(row, Mapping) and isinstance(row.get("id"), str)]
    characters, assets = plan.get("characters"), plan.get("assets")
    if not isinstance(characters, list) or not isinstance(assets, list):
        raise ValueError("SOURCE_INVALID: visual_plan v4 thiếu characters/assets")
    locks = []
    for row in characters:
        if not isinstance(row, Mapping):
            raise ValueError("SOURCE_INVALID: visual_plan.characters không hợp lệ")
        locks.append({
            "character_id": row.get("character_id"),
            "description_lock": row.get("description_lock"),
            "planned_reference_path": row.get("reference_path"),
        })
    prompt_assets = []
    for index, row in enumerate(assets, 1):
        if not isinstance(row, Mapping):
            raise ValueError("SOURCE_INVALID: visual_plan.assets không hợp lệ")
        basename = row.get("basename")
        prompt_assets.append({
            "asset_id": basename.removesuffix(".png") if isinstance(basename, str) else f"asset_{index:04d}",
            "basename": basename, "role": row.get("role"),
            "source_script_ids": row.get("source_script_ids") or script_ids[:1], "character_ids": row.get("character_ids"),
            "brief": row.get("brief"), "landscape_prompt": row.get("landscape_prompt"),
            "portrait_prompt": row.get("portrait_prompt"), "must_show": [], "must_avoid": [],
        })
    style = files.get("visual_bible.txt", b"").decode("utf-8", errors="replace").strip()
    return {
        "image_prompt_version": "1.1", "prompt_version": TARGET_VERSION,
        "source_story": {"schema_version": "4.1.3", "sha256": hashlib.sha256(files["story.json"]).hexdigest()},
        "image_mode": plan.get("image_mode"),
        "prompt_encoding": {
            "standard": "T5-512", "tokenizer_id": "google/t5-v1_1-xxl",
            "max_tokens": 512, "count_scope": "RESOLVED_IMAGE_PROMPT",
            "overflow_policy": "REWRITE",
        },
        "style_lock": style or "Giữ nguyên phong cách hình ảnh của gói nguồn.",
        "characters_prompt": "\n".join(
            str(row.get("description_lock", "")).strip() for row in locks
            if str(row.get("description_lock", "")).strip()
        ) or "Không có mô tả nhân vật bổ sung từ gói nguồn.",
        "character_locks": locks, "assets": prompt_assets,
        "limitations": ["image_prompts.json được dựng deterministic từ visual_plan.json v4."],
    }


def _normalize_visual_reference_state(
    visual: dict[str, Any], files: Mapping[str, bytes],
) -> list[str]:
    """Normalize the v5.2 reference state from canonical paths and real PNG bytes."""
    characters = visual.get("characters")
    if not isinstance(characters, list):
        raise ValueError("SOURCE_INVALID: visual_plan.characters phải là array")
    if not characters:
        visual["reference_mode"] = "DESCRIPTION_ONLY"
        return []
    ready: list[str] = []
    description_only: list[str] = []
    invalid: list[str] = []
    for row in characters:
        if not isinstance(row, dict):
            raise ValueError("SOURCE_INVALID: visual_plan.characters[] phải là object")
        character_id = row.get("character_id")
        identifier = str(character_id or "UNKNOWN")
        canonical = f"characters/{identifier}.png"
        planned = row.get("planned_reference_path")
        path = row.get("reference_path")
        status = row.get("reference_status")
        if planned is None and path is None and status in {None, "NOT_APPLICABLE"}:
            row.update(
                planned_reference_path=None,
                reference_path=None,
                reference_status="NOT_APPLICABLE",
            )
            description_only.append(identifier)
            continue
        if planned != canonical or path != canonical or status != "READY":
            invalid.append(f"{identifier}: path/status không tạo thành READY canonical")
            continue
        raw = files.get(canonical)
        if raw is None:
            invalid.append(f"{identifier}: thiếu {canonical}")
            continue
        try:
            with Image.open(BytesIO(raw)) as image:
                image.verify()
            with Image.open(BytesIO(raw)) as image:
                if image.format != "PNG" or getattr(image, "is_animated", False):
                    raise ValueError("không phải PNG tĩnh")
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            invalid.append(f"{identifier}: reference PNG không hợp lệ ({exc})")
            continue
        ready.append(identifier)
    if invalid:
        raise ValueError("SOURCE_INVALID: " + "; ".join(invalid))
    if ready and description_only:
        raise ValueError(
            "SOURCE_INVALID: không hỗ trợ trộn IMAGE_REFERENCE và DESCRIPTION_ONLY; "
            f"READY={', '.join(ready)}; DESCRIPTION_ONLY={', '.join(description_only)}"
        )
    visual["reference_mode"] = "IMAGE_REFERENCE" if ready else "DESCRIPTION_ONLY"
    return ready


def _image_prompts_to_v520(raw: bytes, story_raw: bytes) -> dict[str, Any]:
    """Project a legacy or partially upgraded plan onto the exact v5.2 root."""
    source = read_json(raw)
    locks = source.get("character_locks")
    if not isinstance(locks, list):
        raise ValueError("SOURCE_INVALID: image_prompts.character_locks phải là array")
    descriptions = [
        str(row.get("description_lock", "")).strip()
        for row in locks
        if isinstance(row, Mapping) and str(row.get("description_lock", "")).strip()
    ]
    characters_prompt = source.get("characters_prompt")
    if not isinstance(characters_prompt, str) or not characters_prompt.strip():
        characters_prompt = "\n".join(descriptions) or "Không có mô tả nhân vật bổ sung từ gói nguồn."
    limitations = source.get("limitations")
    if not isinstance(limitations, list):
        limitations = []
    return {
        "image_prompt_version": "1.1",
        "prompt_version": TARGET_VERSION,
        "source_story": {
            "schema_version": "4.1.3",
            "sha256": hashlib.sha256(story_raw).hexdigest(),
        },
        "image_mode": source.get("image_mode"),
        "prompt_encoding": {
            "standard": "T5-512",
            "tokenizer_id": "google/t5-v1_1-xxl",
            "max_tokens": 512,
            "count_scope": "RESOLVED_IMAGE_PROMPT",
            "overflow_policy": "REWRITE",
        },
        "style_lock": source.get("style_lock"),
        "characters_prompt": characters_prompt.strip(),
        "character_locks": locks,
        "assets": source.get("assets"),
        "limitations": [
            item for item in limitations if isinstance(item, str) and item.strip()
        ],
    }


def _transform_files(members: Mapping[str, bytes], source_version: str, stage: int) -> tuple[dict[str, bytes], list[str]]:
    files = {name: raw for name, raw in members.items() if name != "manifest.json"}
    transformed: list[str] = []

    if source_version.startswith("4."):
        image_prompts = _image_prompts_from_v4(files)
        visual = read_json(files["visual_plan.json"])
        if not isinstance(visual, dict):
            raise ValueError("SOURCE_INVALID: visual_plan root phải là object")
        visual_assets = visual.get("assets")
        if not isinstance(visual_assets, list):
            raise ValueError("SOURCE_INVALID: visual_plan.assets phải là array")
        visible_character_ids = {
            character_id for row in visual_assets if isinstance(row, Mapping)
            for character_id in row.get("character_ids", []) if isinstance(character_id, str)
        }
        original_characters = visual.get("characters")
        if not isinstance(original_characters, list):
            raise ValueError("SOURCE_INVALID: visual_plan.characters phải là array")
        removed_visual_characters = [
            str(row.get("character_id")) for row in original_characters
            if isinstance(row, Mapping) and row.get("character_id") not in visible_character_ids
        ]
        visual["characters"] = [
            row for row in original_characters
            if isinstance(row, Mapping) and row.get("character_id") in visible_character_ids
        ]
        ready_references = _normalize_visual_reference_state(visual, files)
        prompt_sources = {
            row["basename"]: row["source_script_ids"] for row in image_prompts["assets"]
        }
        for row in visual.get("assets", []):
            if isinstance(row, dict) and row.get("basename") in prompt_sources:
                row["source_script_ids"] = prompt_sources[row["basename"]]
        files["visual_plan.json"] = _json_bytes(visual)
        transformed.append("visual_plan.json")
    else:
        image_prompts = _image_prompts_to_v520(
            files["image_prompts.json"], files["story.json"]
        )
    files["image_prompts.json"] = _json_bytes(image_prompts)
    transformed.append("image_prompts.json")

    if source_version.startswith("4."):
        video = read_json(files["video_prompts.json"])
        video["source_mode"] = "STORY_ONLY"
        for clip in video.get("clips", []):
            if isinstance(clip, dict):
                clip["reference_paths"] = []
        files["video_prompts.json"] = _json_bytes(video)
        transformed.append("video_prompts.json")

    source_report = read_json(files["validation_report.json"])
    limitations = [item for item in source_report.get("limitations", []) if isinstance(item, str) and item.strip()]
    remaining = [item for item in source_report.get("remaining_work", []) if isinstance(item, str) and item.strip()]
    remaining.append(f"Chạy lại toàn bộ gate bắt buộc của prompt v{TARGET_VERSION}.")
    if source_version.startswith("4.") and ready_references:
        limitations.append(
            "Migration đã chuẩn hóa visual_plan.reference_mode thành IMAGE_REFERENCE "
            f"sau khi xác minh PNG canonical cho: {', '.join(ready_references)}."
        )
    if source_version.startswith("4.") and removed_visual_characters:
        limitations.append(
            "Migration đã bỏ character dư khỏi visual_plan vì không xuất hiện trong assets: "
            + ", ".join(removed_visual_characters)
            + ". Character lock nguồn vẫn được giữ trong image_prompts.json."
        )
    report = {
        "schema_version": "5.0.0",
        "prompt_version": TARGET_VERSION,
        "stage": stage,
        "status": "PARTIAL",
        "input_sources": [f"Migrated from prompt v{source_version}"],
        "checks": _migration_checks(stage),
        "limitations": limitations,
        "remaining_work": remaining,
        "archive_validation": {"status": "NOT_CHECKED", "details": "Kiểm tra lại sau khi đóng ZIP."},
    }
    files["validation_report.json"] = _json_bytes(report)
    transformed.append("validation_report.json")
    return files, transformed


def migrate_extracted_package(root: Path) -> MigrationResult:
    """Build an immutable v5.2 migration snapshot from an extracted v5 package."""
    root = root.expanduser().resolve()
    members = _directory_members(root)
    source_version, source_stage, stage = _source_identity(members)
    source_contract = prompt_contract_for_version(source_version)
    source_inspection = inspect_directory(root, contract=source_contract)
    failed_checks = [
        row for row in source_inspection.get("checks", []) if row.get("status") == "FAIL"
    ]
    repairable_current = (
        source_version in {"5.2.0", TARGET_VERSION}
        and {row.get("check") for row in failed_checks} <= {"image_prompts"}
    )
    if source_inspection.get("integrity_status") != "PASS" and not repairable_current:
        failures = [str(row.get("detail")) for row in failed_checks]
        raise ValueError("SOURCE_INVALID: " + "; ".join(failures[:5]))

    files, transformed = _transform_files(members, source_version, stage)
    payload, inspection = build_workflow_package(
        stage, "REPAIR", files, contract=prompt_contract_for_version(TARGET_VERSION)
    )
    migrated = read_archive(payload)
    source_hash = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    target_hash = hashlib.sha256(payload).hexdigest()
    preserved = sorted(name for name in files if name not in transformed)
    report = {
        "migration_version": MIGRATION_VERSION,
        "source_prompt_version": source_version,
        "target_prompt_version": TARGET_VERSION,
        "source_manifest_sha256": source_hash,
        "target_package_sha256": target_hash,
        "status": "MIGRATED_WITH_WARNINGS",
        "source_stage": source_stage,
        "target_stage": stage,
        "preserved_files": preserved,
        "transformed_files": transformed,
        "warnings": [f"Các gate v{TARGET_VERSION} được đặt NOT_CHECKED và phải kiểm định lại."],
        "required_actions": [f"Chạy lại toàn bộ gate bắt buộc của prompt v{TARGET_VERSION}."],
    }
    return MigrationResult(
        status="MIGRATED_WITH_WARNINGS", source_version=source_version,
        target_version=TARGET_VERSION, stage=stage,
        archive_name={1: "story_stage1.zip", 2: "story_stage2.zip", 3: "story.zip"}[stage],
        archive_bytes=payload, members=migrated, report=report, inspection=inspection,
    )


def publish_migrated_package(result: MigrationResult, destination: Path) -> Path:
    """Atomically materialize a migration into a new, otherwise empty directory."""
    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Thư mục đích phải mới hoặc đang trống")
    destination.mkdir(parents=True, exist_ok=True)
    for name, raw in result.members.items():
        target = destination / Path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        publish_package_atomic(target, raw)
    publish_package_atomic(destination / result.archive_name, result.archive_bytes)
    publish_package_atomic(destination / "migration_report.json", _json_bytes(result.report))
    return destination


def rebuild_v520_checkpoint_chain(root: Path) -> LineageRebuildResult:
    """Rebuild Stage 1→3 with exact canonical inheritance from a final v5.2 package."""
    root = root.expanduser().resolve()
    members = _directory_members(root)
    manifest = read_json(members["manifest.json"])
    source_version = str(manifest.get("prompt_version") or "")
    if source_version not in {"5.2.0", TARGET_VERSION} or manifest.get("stage") != 3:
        raise ValueError("Chỉ hỗ trợ dựng lại lineage cho package v5.2.x Stage 3")
    source_report = read_json(members["validation_report.json"])
    source_checks = {
        row.get("id"): row for row in source_report.get("checks", [])
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }
    origins = {
        row["path"]: row["origin_stage"] for row in manifest.get("files", [])
        if isinstance(row, Mapping) and isinstance(row.get("path"), str)
        and type(row.get("origin_stage")) is int
    }
    contract = prompt_contract_for_version(source_version)
    archives: dict[str, bytes] = {}
    inspections: dict[int, Mapping[str, Any]] = {}
    parent: Mapping[str, bytes] | None = None
    final_members: Mapping[str, bytes] = {}
    for stage in (1, 2, 3):
        required = sorted(V520_COMMON_GATES | V520_STAGE_GATES[stage])
        checks: list[dict[str, Any]] = []
        for identifier in required:
            existing = source_checks.get(identifier)
            if existing is not None and stage == 3:
                row = dict(existing)
            else:
                row = {
                    "id": identifier,
                    "status": "NOT_CHECKED",
                    "method": sorted(V520_GATE_METHODS[identifier])[0],
                    "required": True,
                    "target": "package",
                    "details": "Cần kiểm định trên checkpoint lineage mới.",
                }
            if identifier == "INHERITED_BYTES":
                row.update(
                    status="PASS", method="CODE",
                    details="Builder đã đối chiếu exact canonical bytes với checkpoint cha trực tiếp.",
                )
            checks.append(row)
        report = {
            "schema_version": "5.0.0", "prompt_version": source_version,
            "stage": stage, "status": "PARTIAL",
            "input_sources": ["Rebuilt lineage from verified Stage 3 payload"],
            "checks": checks,
            "limitations": list(source_report.get("limitations", [])) if stage == 3 else [],
            "remaining_work": list(source_report.get("remaining_work", [])) if stage == 3 else [
                "Chạy lại các gate bắt buộc trên checkpoint lineage mới."
            ],
            "archive_validation": {
                "status": "NOT_CHECKED", "details": "Kiểm tra lại sau khi đóng ZIP."
            },
        }
        files = {
            name: raw for name, raw in members.items()
            if name != "manifest.json" and name != "validation_report.json"
            and origins.get(name, 4) <= stage
        }
        files["validation_report.json"] = _json_bytes(report)
        payload, inspection = build_workflow_package(
            stage, "REPAIR" if stage == 1 else "CREATE", files,
            parent=parent, contract=contract,
        )
        current = read_archive(payload)
        if stage > 1:
            inherited: Mapping[str, Any] = next(
                (row for row in inspection.get("checks", []) if row.get("check") == "inherited_bytes"),
                {},
            )
            if inherited.get("status") != "PASS":
                raise ValueError(f"Stage {stage} không đạt INHERITED_BYTES")
        archive_name = {1: "story_stage1.zip", 2: "story_stage2.zip", 3: "story.zip"}[stage]
        archives[archive_name] = payload
        inspections[stage] = inspection
        parent = current
        final_members = current
    report = {
        "lineage_rebuild_version": "1.0",
        "prompt_version": source_version,
        "status": "REBUILT_WITH_VERIFIED_INHERITANCE",
        "archives": list(archives),
        "source_manifest_sha256": hashlib.sha256(members["manifest.json"]).hexdigest(),
        "stage2_inherited_bytes": "PASS",
        "stage3_inherited_bytes": "PASS",
        "warnings": ["Các gate không có bằng chứng nguồn vẫn giữ NOT_CHECKED."],
    }
    return LineageRebuildResult(archives, final_members, inspections, report)


def publish_rebuilt_checkpoint_chain(result: LineageRebuildResult, destination: Path) -> Path:
    """Publish a rebuilt lineage into a new or empty directory."""
    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Thư mục đích phải mới hoặc đang trống")
    destination.mkdir(parents=True, exist_ok=True)
    for name, raw in result.final_members.items():
        target = destination / Path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        publish_package_atomic(target, raw)
    for name, raw in result.archives.items():
        publish_package_atomic(destination / name, raw)
    publish_package_atomic(destination / "lineage_rebuild_report.json", _json_bytes(result.report))
    return destination


__all__ = [
    "MIGRATION_VERSION", "SUPPORTED_SOURCE_VERSIONS", "TARGET_VERSION", "LineageRebuildResult",
    "MigrationResult", "migrate_extracted_package", "publish_migrated_package",
    "publish_rebuilt_checkpoint_chain", "rebuild_v520_checkpoint_chain",
]
