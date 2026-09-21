"""Deterministic CREATE/REPAIR builder for progressive CURRENT story.zip packages."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from studio.artifact_validation import (
    STORY_VALIDATION_FIELDS,
    validate_story_validation_bytes,
)
from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.video_prompt_validation import (
    normalize_video_prompt_plan,
    validate_video_prompt_plan,
)
from studio.workflow_package import (
    FILE_FIELDS,
    INTEGRITY_CHECKS,
    MANIFEST_FIELDS,
    VALIDATION_FIELDS,
    expected_files,
    inspect_members,
    owner_stage,
    package_digest,
    read_archive,
    read_json,
)


def _json_bytes(value: Any) -> bytes:
    text = unicodedata.normalize("NFC", json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return text.encode("utf-8")


def _current_story_validation_profile(raw: bytes, contract: PromptContract) -> str:
    """Return the profile only after the Stage 1 report passes CURRENT root preflight."""
    report = read_json(raw)
    problems = []
    if tuple(report) != STORY_VALIDATION_FIELDS:
        missing = [name for name in STORY_VALIDATION_FIELDS if name not in report]
        detail = f"; thiếu field: {', '.join(missing)}" if missing else ""
        problems.append(f"field/order không đúng contract CURRENT{detail}")
    if report.get("schema_version") != contract.story_validation_schema_version:
        problems.append(
            f"schema_version={report.get('schema_version')!r}, "
            f"yêu cầu {contract.story_validation_schema_version!r}"
        )
    profile = report.get("active_profile")
    if profile not in {"YOUTH_SAFE", "ADULT_STANDARD", "SERIAL_DETECTIVE"}:
        problems.append(f"active_profile không hợp lệ: {profile!r}")
    if problems:
        raise ValueError("story_validation.json không theo contract CURRENT: " + "; ".join(problems))
    return str(profile)


def build_workflow_package(stage: str, operation: str, files: Mapping[str, bytes], *,
                           parent: Mapping[str, bytes] | None = None,
                           contract: PromptContract | None = None) -> tuple[bytes, dict[str, Any]]:
    """Build into memory, reopen, and return bytes; never mutates a source archive."""
    contract = contract or load_prompt_contract()
    stages = contract.workflow_package_stages
    purposes = contract.workflow_package_purposes
    if stage not in stages or operation not in contract.workflow_operation_modes:
        raise ValueError("Stage/operation ngoài prompt contract")
    index = stages.index(stage)
    purpose_by_stage = (purposes[0], purposes[0], purposes[1], purposes[2])
    if "story.json" not in files:
        raise ValueError("Thiếu story.json")
    if "story_validation.json" not in files:
        raise ValueError("Thiếu story_validation.json")
    active_profile = _current_story_validation_profile(files["story_validation.json"], contract)
    story = read_json(files["story.json"])
    visual_plan = read_json(files["visual_plan.json"]) if "visual_plan.json" in files else None
    expected = expected_files(
        stage, story, "series_anchor.json" in files, contract, visual_plan
    )[1:]
    if list(files) != expected:
        raise ValueError("Input files phải đúng exact allowlist và canonical order của stage")
    files = dict(files)
    if stage == stages[3]:
        try:
            video_plan = read_json(files[contract.video_prompt_file_name])
            normalized_plan = normalize_video_prompt_plan(video_plan, story, contract=contract)
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Stage 4 cần ChatGPT tạo lại video_prompts: {exc}") from exc
        files[contract.video_prompt_file_name] = _json_bytes(normalized_plan)
        validation_result = validate_video_prompt_plan(
            normalized_plan, contract=contract, members=files
        )
        if validation_result["errors"]:
            summary = "; ".join(validation_result["errors"][:5])
            raise ValueError(f"Stage 4 còn lỗi sau hậu xử lý; cần ChatGPT tạo lại: {summary}")
    if stage == stages[0] and operation == "CREATE":
        if parent is not None:
            raise ValueError("Stage 1 CREATE không nhận parent")
        parent_digest = None
    else:
        if parent is None:
            raise ValueError("Stage sau hoặc REPAIR bắt buộc có exact parent package")
        prior = inspect_members(parent, archive=True, contract=contract)
        wanted = stage if operation == "REPAIR" else stages[index - 1]
        # A direct parent can be used without having every ancestor available.
        # This mirrors inspect_members(): all deterministic integrity checks on
        # the supplied parent must pass, except its own parent_binding.
        prior_checks = {
            item.get("check"): item.get("status")
            for item in prior.get("checks", [])
            if item.get("check") in INTEGRITY_CHECKS - {"parent_binding"}
        }
        required = INTEGRITY_CHECKS - {"parent_binding"}
        parent_integrity_ok = set(prior_checks) == required and all(
            prior_checks[name] == "PASS" for name in required
        )
        if not parent_integrity_ok or prior.get("stage") != wanted:
            raise ValueError("Parent package không đúng stage hoặc chưa đạt integrity")
        parent_digest = prior["manifest"].get("package_digest_sha256")
        for name, raw in files.items():
            if owner_stage(name, contract) != stage and parent.get(name) != raw:
                raise ValueError(f"Member kế thừa bị thay đổi bytes: {name}")
    rows = []
    for name in expected:
        raw = files[name]
        owner = owner_stage(name, contract)
        row = dict(zip(FILE_FIELDS, (name, hashlib.sha256(raw).hexdigest(), len(raw), owner,
                                    "CREATED_CURRENT_STAGE" if owner == stage else "READ_ONLY")))
        rows.append(row)
    validation = {name: "PASS" for name in VALIDATION_FIELDS}
    manifest = dict(zip(MANIFEST_FIELDS, (
        contract.workflow_manifest_schema_version, stage, purpose_by_stage[index], operation,
        contract.version_label, active_profile,
        hashlib.sha256(files["story.json"]).hexdigest(), parent_digest,
        stages[index + 1] if index + 1 < len(stages) else None, len(expected) + 1,
        rows, validation, package_digest(rows),
    )))
    members = {"workflow_manifest.json": _json_bytes(manifest), **files}
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in members.items():
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    payload = stream.getvalue()
    inspection = inspect_members(members, archive=True, parent=parent, contract=contract)
    if inspection.get("integrity_status") != "PASS":
        raise ValueError("Package vừa build không vượt reopen integrity gate")
    return payload, inspection


def publish_package_atomic(destination: Path, payload: bytes) -> None:
    """Publish only a completed archive using same-directory atomic replacement."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def publish_story_validation_report(root: Path, payload: bytes) -> dict[str, Any]:
    """Validate a CURRENT report against local authoritative bytes, then publish atomically."""
    root = root.resolve()
    story_path = root / "story.json"
    if not story_path.is_file():
        raise ValueError("Thiếu story.json để đối chiếu báo cáo kiểm định")
    result = validate_story_validation_bytes(
        payload, story_path.read_bytes(), character_root=root,
    )
    if result.status != "PASS":
        raise ValueError("Báo cáo kiểm định không hợp lệ: " + "; ".join(result.errors))
    publish_package_atomic(root / "story_validation.json", payload)
    return result.as_dict()


def _directory_files(root: Path, stage: str, contract: PromptContract) -> dict[str, bytes]:
    """Read exactly the canonical source members for a stage from ``root``."""
    story_path = root / "story.json"
    if not story_path.is_file():
        raise ValueError(f"Thiếu story.json để tạo checkpoint {stage}")
    try:
        story = read_json(story_path.read_bytes())
        visual_plan_path = root / "visual_plan.json"
        visual_plan = (read_json(visual_plan_path.read_bytes()) if visual_plan_path.is_file() else None)
        names = expected_files(
            stage, story, (root / "series_anchor.json").is_file(), contract, visual_plan
        )[1:]
        return {name: (root / name).read_bytes() for name in names}
    except OSError as exc:
        raise ValueError(f"Không thể đọc artifact {stage}: {exc}") from exc


def _publish_manifest(root: Path, payload: bytes) -> None:
    """Materialize only the manifest; all source artifacts were verified in memory."""
    publish_package_atomic(root / "workflow_manifest.json", read_archive(payload)["workflow_manifest.json"])


def _publish_stage4_artifacts(root: Path, payload: bytes, contract: PromptContract) -> None:
    """Publish Stage 4-owned normalized bytes from the verified archive."""
    members = read_archive(payload)
    publish_package_atomic(
        root / contract.video_prompt_file_name,
        members[contract.video_prompt_file_name],
    )


def publish_stage1_checkpoint(root: Path, *, contract: PromptContract | None = None,
                              archive_name: str = "story.zip") -> dict[str, Any]:
    """Create the canonical Stage 1 manifest and archive from an output directory.

    Story generation owns the source artifacts in ``root``.  This function only
    derives the manifest from their exact bytes after the in-memory builder has
    reopened and verified the resulting package.  It is therefore safe to use
    as the final publishing step for a newly generated Stage 1 story and to
    repair an older, pre-CURRENT manifest.
    """
    root = root.resolve()
    contract = contract or load_prompt_contract()
    stage = contract.workflow_package_stages[0]
    files = _directory_files(root, stage, contract)
    payload, inspection = build_workflow_package(stage, "CREATE", files, contract=contract)
    # The manifest and archive are both derived from the same verified bytes.
    # Publish the archive first so a directory never claims a package that was
    # not successfully materialized as story.zip.
    publish_package_atomic(root / archive_name, payload)
    _publish_manifest(root, payload)
    return inspection


def publish_stage2_checkpoint(root: Path, *, contract: PromptContract | None = None) -> dict[str, Any]:
    """Rebuild Stage 2 from the directory and a freshly verified Stage 1 parent.

    A legacy Stage 2 manifest cannot serve as provenance.  Build both archives
    before replacing anything, then preserve the exact Stage 1 parent as
    ``stage1_checkpoint.zip`` and publish Stage 2 as ``story.zip``.
    """
    root = root.resolve()
    contract = contract or load_prompt_contract()
    stage1, stage2 = contract.workflow_package_stages[:2]
    parent_payload, parent_inspection = build_workflow_package(
        stage1, "CREATE", _directory_files(root, stage1, contract), contract=contract
    )
    if parent_inspection.get("integrity_status") != "PASS":
        raise ValueError("Không thể tạo parent Stage 1 hợp lệ")
    parent = read_archive(parent_payload)
    payload, inspection = build_workflow_package(
        stage2, "CREATE", _directory_files(root, stage2, contract), parent=parent, contract=contract
    )
    publish_package_atomic(root / "stage1_checkpoint.zip", parent_payload)
    publish_package_atomic(root / "story.zip", payload)
    _publish_manifest(root, payload)
    return inspection


def publish_stage4_release(root: Path, parent: Mapping[str, bytes], *,
                           contract: PromptContract | None = None) -> dict[str, Any]:
    """Rebuild Stage 4 from a verified, authoritative Stage 3 package.

    The Stage 4 directory must retain the Stage 2 Visual Bible.  This entry
    point nevertheless requires the direct Stage 3 parent, so the builder can
    byte-compare every inherited member instead of inventing provenance.
    """
    root = root.resolve()
    contract = contract or load_prompt_contract()
    stage = contract.workflow_package_stages[3]
    current_parent = parent
    migrated_parent_payload: bytes | None = None
    try:
        payload, inspection = build_workflow_package(
            stage, "CREATE", _directory_files(root, stage, contract),
            parent=current_parent, contract=contract,
        )
    except ValueError as original_error:
        # Prompt 3.16.11 Stage 3 packages used a legacy manifest and did not
        # persist visual_bible.json. Admit them only as migration evidence:
        # every declared member must verify and match the local inherited byte,
        # after which a complete CURRENT parent chain is rebuilt in memory.
        manifest = read_json(parent.get("workflow_manifest.json", b"{}"))
        rows = manifest.get("files")
        legacy_ok = (
            manifest.get("package_stage") == contract.workflow_package_stages[2]
            and isinstance(rows, list) and bool(rows)
            and all(isinstance(row, dict) and tuple(row) == FILE_FIELDS for row in rows)
            and set(parent) == {"workflow_manifest.json", *(row["path"] for row in rows)}
            and all(
                row["path"] in parent
                and hashlib.sha256(parent[row["path"]]).hexdigest() == row["sha256"]
                and len(parent[row["path"]]) == row["size_bytes"]
                for row in rows
            )
            and hashlib.sha256(parent.get("story.json", b"")).hexdigest()
                == manifest.get("story_sha256")
        )
        current_stage3_files = _directory_files(root, contract.workflow_package_stages[2], contract)
        inherited_match = legacy_ok and all(
            current_stage3_files.get(name) == raw
            for name, raw in parent.items() if name != "workflow_manifest.json"
        )
        if not inherited_match:
            raise original_error

        chain_parent: Mapping[str, bytes] | None = None
        for chain_stage in contract.workflow_package_stages[:3]:
            migrated_parent_payload, _ = build_workflow_package(
                chain_stage, "CREATE", _directory_files(root, chain_stage, contract),
                parent=chain_parent, contract=contract,
            )
            chain_parent = read_archive(migrated_parent_payload)
        current_parent = chain_parent
        payload, inspection = build_workflow_package(
            stage, "CREATE", _directory_files(root, stage, contract),
            parent=current_parent, contract=contract,
        )
    if migrated_parent_payload is not None:
        publish_package_atomic(root / "stage3_release.zip", migrated_parent_payload)
    publish_package_atomic(root / "stage4_release.zip", payload)
    publish_package_atomic(root / "story.zip", payload)
    _publish_stage4_artifacts(root, payload, contract)
    _publish_manifest(root, payload)
    return inspection


def rebuild_checkpoint_chain(root: Path, target_stage: str, *,
                             contract: PromptContract | None = None) -> dict[str, Any]:
    """Rebuild CURRENT packages from Stage 1 through ``target_stage``.

    Each package is constructed in memory from the source artifacts and the
    exact bytes of the preceding package.  Nothing is published until every
    stage has passed its integrity gate, preventing a half-rebuilt chain.
    """
    root = root.resolve()
    contract = contract or load_prompt_contract()
    stages = contract.workflow_package_stages
    if target_stage not in stages:
        raise ValueError("Target stage ngoài workflow contract")
    target_index = stages.index(target_stage)
    payloads: list[tuple[str, bytes]] = []
    parent: Mapping[str, bytes] | None = None
    inspection: dict[str, Any] | None = None
    for stage in stages[:target_index + 1]:
        payload, inspection = build_workflow_package(
            stage, "CREATE", _directory_files(root, stage, contract),
            parent=parent, contract=contract,
        )
        parent = read_archive(payload)
        payloads.append((stage, payload))
    names = {
        stages[0]: "stage1_checkpoint.zip",
        stages[1]: "stage2_checkpoint.zip",
        stages[2]: "stage3_release.zip",
        stages[3]: "stage4_release.zip",
    }
    for stage, payload in payloads:
        publish_package_atomic(root / names[stage], payload)
    publish_package_atomic(root / "story.zip", payloads[-1][1])
    if target_stage == stages[3]:
        _publish_stage4_artifacts(root, payloads[-1][1], contract)
    _publish_manifest(root, payloads[-1][1])
    if inspection is None:  # Defensive; a valid contract always has a Stage 1.
        raise ValueError("Không có checkpoint để publish")
    return inspection


__all__ = [
    "build_workflow_package", "publish_package_atomic", "publish_story_validation_report",
    "publish_stage1_checkpoint",
    "publish_stage2_checkpoint", "publish_stage4_release", "rebuild_checkpoint_chain",
]
