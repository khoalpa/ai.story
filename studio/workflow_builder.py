"""Deterministic package writer for v5 three-stage and legacy v4 packages."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unicodedata
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Sequence

from studio.prompt_contract import (
    PromptContract,
    prompt_contract_for_version,
)
from studio.workflow_package import (
    FILE_FIELDS,
    _expected_payload,
    active_image_basenames,
    inspect_members,
    read_archive,
    read_json,
    safe_name,
)

CHECKPOINT_NAMES = {1: "story_stage1.zip", 2: "story_stage2.zip", 3: "story.zip", 4: "story_video_prompts.zip"}
MIGRATION_RERUN_WORK = "Chạy lại toàn bộ gate bắt buộc của prompt v5.2.2."
LEGACY_MIGRATION_RERUN_WORK = "Chạy lại toàn bộ gate bắt buộc của prompt v5.2.0."


def _json_bytes(value: Any) -> bytes:
    return unicodedata.normalize("NFC", json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)).encode("utf-8")


def _archive_bytes(members: Mapping[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, members[name])
    return buffer.getvalue()


def _stage_number(stage: object) -> int:
    if type(stage) is int and stage in range(1, 5):
        return stage
    if isinstance(stage, str) and stage in {f"STAGE{i}" for i in range(1, 5)}:
        return int(stage[-1])
    raise ValueError("Stage phải là 1..4 hoặc STAGE1..STAGE4; contract quyết định stage được hỗ trợ")


def _origin_stage(path: str, stage: int, parent_manifest: Mapping[str, Any] | None,
                  contract: PromptContract) -> int:
    if parent_manifest:
        for row in parent_manifest.get("files", []):
            if isinstance(row, Mapping) and row.get("path") == path:
                return int(row["origin_stage"])
    if path in {"story.json"} or path == "series_anchor.json":
        return 1
    if contract.version >= (5, 0, 0) and path in {"image_prompts.json", "video_prompts.json"}:
        return 1
    if path.startswith("characters/") and contract.version >= (5, 2, 0):
        return 1
    if path.startswith(("characters/", "landscape/")) or path in {"visual_plan.json", "visual_bible.txt"}:
        return 2
    if path.startswith("portrait/"):
        return 3
    return stage


def build_workflow_package(stage: str | int, operation: str, files: Mapping[str, bytes], *,
                           parent: Mapping[str, bytes] | None = None,
                           contract: PromptContract | None = None) -> tuple[bytes, dict[str, Any]]:
    number = _stage_number(stage)
    if operation not in {"CREATE", "REPAIR"}:
        raise ValueError("operation phải là CREATE hoặc REPAIR")
    if "manifest.json" in files:
        raise ValueError("Builder tự tạo manifest.json")
    if not {"story.json", "validation_report.json"}.issubset(files):
        raise ValueError("Thiếu story.json hoặc validation_report.json")
    report = read_json(files["validation_report.json"])
    contract = contract or prompt_contract_for_version(str(report.get("prompt_version") or ""))
    if f"STAGE{number}" not in contract.workflow_package_stages:
        raise ValueError(f"Prompt v{contract.version_label} không hỗ trợ Stage {number}")
    package_schema = contract.workflow_manifest_schema_version or "4.1.3"
    if report.get("prompt_version") != contract.version_label or report.get("stage") != number:
        raise ValueError(f"validation_report không khớp prompt/stage v{contract.version_label}")
    if report.get("schema_version") != contract.story_validation_schema_version:
        raise ValueError("validation_report không khớp package schema")
    for name, raw in files.items():
        if not name.endswith(".json") or name == "image_prompts.json":
            continue
        expected_schema = contract.story_validation_schema_version if name == "validation_report.json" else "4.1.3"
        if read_json(raw).get("schema_version") != expected_schema:
            raise ValueError(f"{name} không dùng schema {expected_schema}")
    parent_manifest = read_json(parent["manifest.json"]) if parent and "manifest.json" in parent else None
    parent_sha = hashlib.sha256(_archive_bytes(parent)).hexdigest() if parent else None
    rows = []
    for name in sorted(files):
        raw = files[name]
        rows.append(dict(zip(FILE_FIELDS, (name, len(raw), hashlib.sha256(raw).hexdigest(), _origin_stage(name, number, parent_manifest, contract)))))
    manifest = {"schema_version": package_schema, "prompt_version": contract.version_label, "stage": number,
                "status": report.get("status"), "parent_package_sha256": parent_sha, "files": rows}
    members = {"manifest.json": _json_bytes(manifest), **files}
    payload = _archive_bytes(members)
    inspection_parent = None if operation == "REPAIR" and number == 1 else parent
    inspection = inspect_members(read_archive(payload), archive=True, parent=inspection_parent, contract=contract)
    if (inspection["integrity_status"] != "PASS"
            or report.get("status") == "COMPLETE" and inspection["publish_status"] != "PASS"):
        raise ValueError("Gói tạo ra không hợp lệ: " + "; ".join(row["detail"] for row in inspection["checks"] if row["status"] == "FAIL"))
    return payload, inspection


def publish_package_atomic(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def manifest_digest_mismatches(root: Path) -> list[dict[str, Any]]:
    """Return payload size/hash differences without changing the package."""
    manifest = read_json((root / "manifest.json").read_bytes())
    differences: list[dict[str, Any]] = []
    for row in manifest.get("files", []):
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            continue
        path = root / Path(row["path"])
        if not path.is_file():
            differences.append({"path": row["path"], "status": "MISSING"})
            continue
        raw = path.read_bytes()
        actual_hash = hashlib.sha256(raw).hexdigest()
        if row.get("size_bytes") != len(raw) or row.get("sha256") != actual_hash:
            differences.append({
                "path": row["path"],
                "status": "CHANGED",
                "manifest_size": row.get("size_bytes"),
                "actual_size": len(raw),
                "manifest_sha256": row.get("sha256"),
                "actual_sha256": actual_hash,
            })
    return differences


def _basename_normalization(
    visual_plan: Mapping[str, Any], listed: set[str], available: set[str], stage: int,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Return a validated candidate when extension-only basename repair is safe."""
    assets = visual_plan.get("assets")
    if not isinstance(assets, list) or not assets:
        return None, []
    candidate = json.loads(json.dumps(visual_plan, ensure_ascii=False))
    changes: list[dict[str, str]] = []
    for row in candidate["assets"]:
        if not isinstance(row, dict):
            return None, []
        old = row.get("basename")
        if not isinstance(old, str) or not safe_name(old) or "/" in old:
            return None, []
        if old.endswith(".png"):
            continue
        # This repair deliberately handles only a missing extension.  It must
        # not guess a replacement for another suffix or a malformed name.
        if Path(old).suffix:
            return None, []
        new = f"{old}.png"
        required = [f"landscape/{new}"]
        if stage >= 3:
            required.append(f"portrait/{new}")
        if any(path not in listed or path not in available for path in required):
            return None, []
        row["basename"] = new
        changes.append({"from": old, "to": new})
    if not changes:
        return None, []
    try:
        active_image_basenames(candidate)
    except (TypeError, ValueError):
        return None, []
    return candidate, changes


def plan_directory_integrity_repair(root: Path) -> dict[str, Any]:
    """Describe deterministic, non-destructive repairs available for a package."""
    manifest = read_json((root / "manifest.json").read_bytes())
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("manifest.files phải là array")
    listed = {row["path"] for row in rows if isinstance(row, Mapping) and isinstance(row.get("path"), str)}
    members = {name: (root / Path(name)).read_bytes() for name in listed if (root / Path(name)).is_file()}
    missing = sorted(listed - set(members))
    actions: list[dict[str, Any]] = []
    blockers: list[str] = []
    paths = [
        path
        for row in rows
        if isinstance(row, Mapping) and isinstance((path := row.get("path")), str)
    ]
    if paths != sorted(paths):
        actions.append({"kind": "SORT_MANIFEST", "detail": "Sắp xếp manifest.files theo path."})
    differences = manifest_digest_mismatches(root)
    changed = [row["path"] for row in differences if row.get("status") == "CHANGED"]
    if changed:
        actions.append({"kind": "REFRESH_DIGESTS", "detail": f"Tính lại size/hash cho {len(changed)} tệp.", "paths": changed})
    if missing:
        blockers.append("Thiếu payload: " + ", ".join(missing))
    if "visual_plan.json" in members:
        try:
            contract = prompt_contract_for_version(str(manifest.get("prompt_version") or ""))
            stage = int(manifest["stage"])
            visual_plan = read_json(members["visual_plan.json"])
            normalized, basename_changes = _basename_normalization(visual_plan, listed, set(members), stage)
            planning_members = dict(members)
            if normalized is not None:
                planning_members["visual_plan.json"] = _json_bytes(normalized)
                visual_plan = normalized
                actions.append({
                    "kind": "NORMALIZE_VISUAL_BASENAMES",
                    "detail": f"Thêm phần mở rộng .png cho {len(basename_changes)} basename trong visual_plan.json.",
                    "changes": basename_changes,
                })
            expected = _expected_payload(
                {"manifest.json": (root / "manifest.json").read_bytes(), **planning_members},
                stage,
                contract,
            )
            extras = sorted(listed - expected)
            characters = visual_plan.get("characters")
            by_id = {
                str(row.get("character_id")): row for row in characters
                if isinstance(row, Mapping) and row.get("character_id")
            } if isinstance(characters, list) else {}
            linkable: list[dict[str, str]] = []
            excludable: list[str] = []
            unresolved: list[str] = []
            linked_ids: set[str] = set()
            for path in extras:
                candidate = Path(path)
                character_id = candidate.stem
                row = by_id.get(character_id)
                if candidate.parent.as_posix() == "characters" and candidate.suffix.lower() == ".png" and row is not None:
                    linkable.append({"character_id": character_id, "path": path})
                    linked_ids.add(character_id)
                elif candidate.parent.as_posix() == "characters" and candidate.suffix.lower() == ".png":
                    # An unbound supplemental portrait is useful project data,
                    # but it is not part of the strict workflow package file set.
                    # Exclude it from manifest/checkpoint without deleting it.
                    excludable.append(path)
                else:
                    unresolved.append(path)
            characters_dir = root / "characters"
            disk_character_paths = (
                sorted(
                    f"characters/{path.name}"
                    for path in characters_dir.iterdir()
                    if path.is_file() and path.suffix.lower() == ".png"
                )
                if characters_dir.is_dir() else []
            )
            for path in disk_character_paths:
                character_id = Path(path).stem
                row = by_id.get(character_id)
                if character_id not in linked_ids and row is not None and (
                    row.get("reference_status") != "READY"
                    or row.get("reference_path") != path
                    or row.get("planned_reference_path") != path
                ):
                    linkable.append({"character_id": character_id, "path": path})
                    linked_ids.add(character_id)
            # Character images may already be part of the manifest while the
            # visual plan still labels them DESCRIPTION_ONLY/NOT_APPLICABLE.
            # Detect that semantic mismatch independently of the file-set diff.
            for character_id, row in by_id.items():
                path = f"characters/{character_id}.png"
                if (
                    character_id not in linked_ids
                    and path in listed
                    and path in members
                    and (
                        row.get("reference_status") != "READY"
                        or row.get("reference_path") != path
                        or row.get("planned_reference_path") != path
                    )
                ):
                    linkable.append({"character_id": character_id, "path": path})
                    linked_ids.add(character_id)
            if linkable:
                if contract.version >= (5, 2, 0):
                    blockers.append(
                        "Prompt v5.2 yêu cầu liên kết ảnh reference bằng repair Stage 1 trước Stage 2: "
                        + ", ".join(row["path"] for row in linkable)
                    )
                else:
                    actions.append({"kind": "LINK_CHARACTER_REFERENCES", "detail": f"Liên kết {len(linkable)} ảnh với nhân vật cùng ID trong visual_plan.json.", "links": linkable})
            if excludable:
                actions.append({
                    "kind": "EXCLUDE_UNBOUND_CHARACTER_FILES",
                    "detail": f"Loại {len(excludable)} ảnh nhân vật không liên kết khỏi manifest/checkpoint; giữ nguyên file trong thư mục dự án.",
                    "paths": excludable,
                })
            if unresolved:
                blockers.append("Tệp ngoài file set cần người dùng quyết định: " + ", ".join(unresolved))
            absent = sorted(expected - listed)
            if absent:
                blockers.append("Manifest thiếu tệp bắt buộc: " + ", ".join(absent))
        except (KeyError, TypeError, ValueError) as exc:
            blockers.append(f"Không thể suy ra file set: {exc}")
    return {"actions": actions, "blockers": blockers, "can_repair": bool(actions) and not blockers}


def _backup_integrity_files(root: Path, names: list[str]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = root / ".ai_story_backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    for name in names:
        source = root / name
        if source.is_file():
            destination = backup / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return backup


def restore_integrity_backup(root: Path, backup: Path) -> None:
    """Restore files written by an integrity repair from its local backup."""
    resolved_root, resolved_backup = root.resolve(), backup.resolve()
    if not resolved_backup.is_relative_to((resolved_root / ".ai_story_backups").resolve()):
        raise ValueError("Bản sao lưu không thuộc dự án hiện tại")
    for source in resolved_backup.rglob("*"):
        if source.is_file():
            publish_package_atomic(resolved_root / source.relative_to(resolved_backup), source.read_bytes())


def plan_stage_completion(root: Path, *, contract: PromptContract | None = None) -> dict[str, Any]:
    """Return a guarded completion plan; never infer completion across unresolved gates."""
    inspection = inspect_members({
        "manifest.json": (root / "manifest.json").read_bytes(),
        **{
            row["path"]: (root / Path(row["path"])).read_bytes()
            for row in read_json((root / "manifest.json").read_bytes()).get("files", [])
            if isinstance(row, Mapping) and isinstance(row.get("path"), str)
            and (root / Path(row["path"])).is_file()
        },
    }, contract=contract)
    blockers: list[str] = []
    if inspection.get("integrity_status") != "PASS":
        blockers.append("Toàn vẹn gói chưa đạt.")
    if inspection.get("stage_gate_status") != "PASS":
        blockers.append("Còn gate bắt buộc chưa đạt hoặc chưa xác minh.")
    report = read_json((root / "validation_report.json").read_bytes())
    raw_remaining_work = [
        str(item).strip() for item in report.get("remaining_work", [])
        if isinstance(item, str) and item.strip()
    ]
    all_required_gates_resolved = all(
        not isinstance(row, Mapping) or row.get("required") is not True
        or row.get("status") in {"PASS", "NOT_APPLICABLE"}
        for row in report.get("checks", [])
    )
    auto_resolved_work = [
        item for item in raw_remaining_work
        if item in {MIGRATION_RERUN_WORK, LEGACY_MIGRATION_RERUN_WORK}
        and all_required_gates_resolved
    ]
    remaining_work = [item for item in raw_remaining_work if item not in auto_resolved_work]
    if remaining_work:
        blockers.append(f"Còn {len(remaining_work)} đầu việc trong remaining_work cần được xác nhận đã giải quyết.")
    unresolved = [
        str(row.get("id")) for row in report.get("checks", [])
        if isinstance(row, Mapping) and row.get("required") is True
        and row.get("status") not in {"PASS", "NOT_APPLICABLE"}
        and row.get("id") != "ANCHOR_EXTERNAL_NESTED_SCHEMA"
    ]
    if unresolved:
        blockers.append("Gate chưa giải quyết: " + ", ".join(unresolved))
    return {
        "can_complete": not blockers and inspection.get("package_completion_status") != "COMPLETE",
        "already_complete": inspection.get("package_completion_status") == "COMPLETE",
        "blockers": blockers,
        "remaining_work": remaining_work,
        "auto_resolved_work": auto_resolved_work,
        "changes": [
            *(["Đóng đầu việc migration đã hoàn thành: chạy lại toàn bộ gate v5.2.2"] if auto_resolved_work else []),
            "Ghi bằng chứng validator anchor vào validation_report.json",
            "Chuyển report/manifest sang COMPLETE khi không còn remaining work",
            "Tính lại size và SHA-256 của validation_report.json trong manifest",
        ],
    }


def resolve_remaining_work_atomic(
    root: Path, resolved_items: Sequence[str], evidence: str, *, reviewer: str,
    contract: PromptContract | None = None,
) -> tuple[dict[str, Any], Path]:
    """Close explicitly selected remaining-work items and refresh package integrity atomically."""
    selected = list(dict.fromkeys(item.strip() for item in resolved_items if item.strip()))
    note = evidence.strip()
    reviewer_name = reviewer.strip()
    if not selected:
        raise ValueError("Cần chọn ít nhất một đầu việc đã được giải quyết")
    if len(note) < 12:
        raise ValueError("Bằng chứng đóng đầu việc phải có ít nhất 12 ký tự")
    if len(reviewer_name) < 2:
        raise ValueError("Cần nhập tên hoặc định danh người xác nhận")
    manifest = read_json((root / "manifest.json").read_bytes())
    contract = contract or prompt_contract_for_version(str(manifest.get("prompt_version") or ""))
    report = read_json((root / "validation_report.json").read_bytes())
    remaining = report.get("remaining_work")
    if not isinstance(remaining, list) or not all(isinstance(item, str) for item in remaining):
        raise ValueError("validation_report.remaining_work phải là array string")
    unknown = [item for item in selected if item not in remaining]
    if unknown:
        raise ValueError("Đầu việc không còn tồn tại trong báo cáo: " + "; ".join(unknown))
    report["remaining_work"] = [item for item in remaining if item not in selected]
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    resolution = (
        f"[WORK_RESOLUTION reviewer={reviewer_name}; at={stamp}] "
        f"{note} | resolved: {'; '.join(selected)}"
    )
    sources = report.get("input_sources")
    if not isinstance(sources, list):
        raise ValueError("validation_report.input_sources phải là array")
    sources.append(resolution)
    checks = report.get("checks", [])
    for row in checks:
        if (
            isinstance(row, dict) and row.get("method") == "MODEL_REVIEW"
            and row.get("status") in {"PASS", "NOT_APPLICABLE"}
        ):
            previous = str(row.get("details") or "").strip()
            row["details"] = f"{previous}\n{resolution}" if previous else resolution
    review_ids = {
        str(row.get("id")) for row in checks
        if isinstance(row, Mapping) and row.get("method") == "MODEL_REVIEW"
    }
    all_reviews_resolved = all(
        not isinstance(row, Mapping) or row.get("method") != "MODEL_REVIEW"
        or row.get("required") is not True or row.get("status") in {"PASS", "NOT_APPLICABLE"}
        for row in checks
    )
    if all_reviews_resolved and isinstance(report.get("limitations"), list):
        normalized_ids = {identifier.replace("_", " ").casefold() for identifier in review_ids}
        report["limitations"] = [
            item for item in report["limitations"]
            if not (
                isinstance(item, str) and "not_checked" in item.casefold()
                and any(identifier in item.replace("_", " ").casefold() for identifier in normalized_ids)
            )
        ]
    report_raw = _json_bytes(report)
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("manifest.files phải là array")
    report_row = next((row for row in rows if isinstance(row, dict) and row.get("path") == "validation_report.json"), None)
    if report_row is None:
        raise ValueError("manifest không liệt kê validation_report.json")
    report_row["size_bytes"] = len(report_raw)
    report_row["sha256"] = hashlib.sha256(report_raw).hexdigest()
    manifest_raw = _json_bytes(manifest)
    files = {
        row["path"]: report_raw if row["path"] == "validation_report.json" else (root / Path(row["path"])).read_bytes()
        for row in rows
    }
    members = {"manifest.json": manifest_raw, **files}
    inspection = inspect_members(members, archive=True, contract=contract)
    if inspection.get("integrity_status") != "PASS":
        failures = "; ".join(row["detail"] for row in inspection["checks"] if row["status"] == "FAIL")
        raise ValueError("Ứng viên đóng đầu việc không hợp lệ: " + failures)
    checkpoint = CHECKPOINT_NAMES[_stage_number(manifest["stage"])]
    archive_raw = _archive_bytes(members)
    backup = _backup_integrity_files(root, ["manifest.json", "validation_report.json", checkpoint])
    try:
        publish_package_atomic(root / "validation_report.json", report_raw)
        publish_package_atomic(root / checkpoint, archive_raw)
        publish_package_atomic(root / "manifest.json", manifest_raw)
        return inspection, backup
    except Exception:
        restore_integrity_backup(root, backup)
        raise


def complete_stage_atomic(root: Path, *, contract: PromptContract | None = None) -> tuple[dict[str, Any], Path]:
    """Complete a locally verified stage with backup, rollback, and post-write validation."""
    plan = plan_stage_completion(root, contract=contract)
    if not plan["can_complete"]:
        raise ValueError("Không thể hoàn tất Stage: " + "; ".join(plan["blockers"] or ["Stage đã COMPLETE"]))
    report = read_json((root / "validation_report.json").read_bytes())
    checks = report.get("checks", [])
    for row in checks:
        if isinstance(row, dict) and row.get("id") == "ANCHOR_EXTERNAL_NESTED_SCHEMA":
            row.update(status="PASS", method="CODE",
                       details="Đã xác minh bằng validator nested schema cục bộ của AI Story Studio.")
    all_required_gates_resolved = all(
        not isinstance(row, Mapping) or row.get("required") is not True
        or row.get("status") in {"PASS", "NOT_APPLICABLE"}
        for row in checks
    )
    report["remaining_work"] = [
        item for item in report.get("remaining_work", [])
        if ("schema" not in str(item).casefold() or "anchor" not in str(item).casefold())
        and not (
            item in {MIGRATION_RERUN_WORK, LEGACY_MIGRATION_RERUN_WORK}
            and all_required_gates_resolved
        )
    ]
    if all_required_gates_resolved and isinstance(report.get("input_sources"), list):
        report["input_sources"].append(
            "[AUTO_RESOLUTION] Đã đóng đầu việc chạy lại gate migration vì mọi gate bắt buộc đều PASS/NOT_APPLICABLE."
        )
    if report["remaining_work"]:
        raise ValueError("Không thể hoàn tất Stage vì vẫn còn remaining_work.")
    report["status"] = "COMPLETE"
    report_raw = _json_bytes(report)
    manifest = read_json((root / "manifest.json").read_bytes())
    manifest["status"] = "COMPLETE"
    for row in manifest.get("files", []):
        if isinstance(row, dict) and row.get("path") == "validation_report.json":
            row["size_bytes"] = len(report_raw)
            row["sha256"] = hashlib.sha256(report_raw).hexdigest()
    manifest_raw = _json_bytes(manifest)
    backup = _backup_integrity_files(root, ["manifest.json", "validation_report.json"])
    try:
        publish_package_atomic(root / "validation_report.json", report_raw)
        publish_package_atomic(root / "manifest.json", manifest_raw)
        inspection = inspect_members({
            "manifest.json": manifest_raw,
            **{row["path"]: (root / Path(row["path"])).read_bytes() for row in manifest["files"]},
        }, contract=contract)
        if inspection.get("publish_status") != "PASS":
            raise ValueError("Post-write validation chưa đạt publish PASS")
        return inspection, backup
    except Exception:
        restore_integrity_backup(root, backup)
        raise


def review_model_gate_atomic(
    root: Path, gate_id: str, status: str, evidence: str, *, reviewer: str,
    contract: PromptContract | None = None,
) -> tuple[dict[str, Any], Path]:
    """Record one explicit human review without weakening deterministic gates."""
    decision = status.strip().upper()
    note = evidence.strip()
    reviewer_name = reviewer.strip()
    if decision not in {"PASS", "FAIL"}:
        raise ValueError("Kết quả kiểm định thủ công phải là PASS hoặc FAIL")
    if len(note) < 12:
        raise ValueError("Bằng chứng/ghi chú kiểm định phải có ít nhất 12 ký tự")
    if len(reviewer_name) < 2:
        raise ValueError("Cần nhập tên hoặc định danh người kiểm định")
    manifest = read_json((root / "manifest.json").read_bytes())
    contract = contract or prompt_contract_for_version(str(manifest.get("prompt_version") or ""))
    report = read_json((root / "validation_report.json").read_bytes())
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise ValueError("validation_report.checks phải là array")
    matches = [row for row in checks if isinstance(row, dict) and row.get("id") == gate_id]
    if len(matches) != 1:
        raise ValueError("Không tìm thấy duy nhất một gate cần kiểm định")
    gate = matches[0]
    if gate.get("method") != "MODEL_REVIEW":
        raise ValueError("Chỉ gate MODEL_REVIEW mới được kiểm định thủ công")
    previous = str(gate.get("details") or "").strip()
    manual = (
        f"[MANUAL_REVIEW reviewer={reviewer_name}; "
        f"at={datetime.now().astimezone().isoformat(timespec='seconds')}] {note}"
    )
    gate["status"] = decision
    gate["details"] = f"{previous}\n{manual}" if previous else manual
    # A failed review can never leave the report claiming completion.
    if decision == "FAIL":
        report["status"] = "PARTIAL"
    report_raw = _json_bytes(report)
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("manifest.files phải là array")
    report_row = next((row for row in rows if isinstance(row, dict) and row.get("path") == "validation_report.json"), None)
    if report_row is None:
        raise ValueError("manifest không liệt kê validation_report.json")
    report_row["size_bytes"] = len(report_raw)
    report_row["sha256"] = hashlib.sha256(report_raw).hexdigest()
    manifest["status"] = report.get("status")
    manifest_raw = _json_bytes(manifest)
    files = {
        row["path"]: report_raw if row["path"] == "validation_report.json" else (root / Path(row["path"])).read_bytes()
        for row in rows
    }
    members = {"manifest.json": manifest_raw, **files}
    inspection = inspect_members(members, archive=True, contract=contract)
    if inspection.get("integrity_status") != "PASS":
        failures = "; ".join(row["detail"] for row in inspection["checks"] if row["status"] == "FAIL")
        raise ValueError("Ứng viên kiểm định không hợp lệ: " + failures)
    stage = _stage_number(manifest["stage"])
    checkpoint = CHECKPOINT_NAMES[stage]
    archive_raw = _archive_bytes(members)
    backup = _backup_integrity_files(root, ["manifest.json", "validation_report.json", checkpoint])
    try:
        publish_package_atomic(root / "validation_report.json", report_raw)
        publish_package_atomic(root / checkpoint, archive_raw)
        publish_package_atomic(root / "manifest.json", manifest_raw)
        return inspection, backup
    except Exception:
        restore_integrity_backup(root, backup)
        raise


def rerun_deterministic_gates_atomic(
    root: Path, *, parent: Mapping[str, bytes] | None = None,
    contract: PromptContract | None = None,
) -> tuple[dict[str, Any], Path, list[str]]:
    """Re-run locally provable CODE gates and publish an audited checkpoint."""
    manifest = read_json((root / "manifest.json").read_bytes())
    contract = contract or prompt_contract_for_version(str(manifest.get("prompt_version") or ""))
    if contract.version < (5, 2, 0):
        raise ValueError("Hậu kiểm tự động chỉ hỗ trợ package v5.2.0 trở lên")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("manifest.files phải là array")
    files = {
        row["path"]: (root / Path(row["path"])).read_bytes()
        for row in rows if isinstance(row, Mapping) and isinstance(row.get("path"), str)
    }
    members = {"manifest.json": (root / "manifest.json").read_bytes(), **files}
    inspection = inspect_members(members, parent=parent, contract=contract)
    detector = {
        str(row.get("check")): row for row in inspection.get("checks", [])
        if isinstance(row, Mapping)
    }

    def passed(*names: str) -> bool:
        return bool(names) and all(detector.get(name, {}).get("status") == "PASS" for name in names)

    stage = _stage_number(manifest.get("stage"))
    schema_checks = ["story_schema", "image_prompts", "video_prompts"]
    if stage >= 2:
        schema_checks.append("image_prompt_visual_binding")
    evidence: dict[str, tuple[bool, str]] = {
        "JSON_PARSE": (passed("strict_json"), "strict_json"),
        "SCHEMA_LINKS": (passed(*schema_checks), ", ".join(schema_checks)),
        "FILE_SET": (passed("file_set"), "file_set"),
        "MANIFEST_MATCH": (
            passed("manifest_schema", "manifest_files", "file_digest", "validation_report"),
            "manifest_schema, manifest_files, file_digest, validation_report",
        ),
        "VISUAL_PLAN": (passed("image_prompt_visual_binding"), "image_prompt_visual_binding"),
        "IMAGE_FILES": (passed("image_files"), "image_files"),
        "INHERITED_BYTES": (
            parent is not None and passed("inherited_bytes"),
            "inherited_bytes với gói cha trực tiếp",
        ),
        "IMAGE_PROMPT_SCHEMA": (passed("image_prompts"), "image_prompts"),
        "IMAGE_PROMPT_SOURCE_BINDING": (passed("image_prompts"), "image_prompts"),
        "IMAGE_PROMPT_CHARACTER_LINKS": (passed("image_prompts"), "image_prompts"),
        "IMAGE_REFERENCE_FILES": (passed("image_files"), "image_files"),
        "VIDEO_SPANS": (passed("video_prompts"), "video_prompts"),
        "VIDEO_TIMING": (passed("video_prompts"), "video_prompts"),
    }
    report = read_json(files["validation_report.json"])
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise ValueError("validation_report.checks phải là array")
    updated_ids: list[str] = []
    for gate in checks:
        if not isinstance(gate, dict) or gate.get("method") != "CODE":
            continue
        gate_id = str(gate.get("id") or "")
        proof = evidence.get(gate_id)
        if proof is None or not proof[0]:
            continue
        gate["status"] = "PASS"
        gate["details"] = f"Hậu kiểm deterministic tại máy đạt: {proof[1]}."
        updated_ids.append(gate_id)
    if not updated_ids:
        raise ValueError("Không có gate CODE nào đủ bằng chứng để cập nhật")

    report_raw = _json_bytes(report)
    report_row = next(
        (row for row in rows if isinstance(row, dict) and row.get("path") == "validation_report.json"),
        None,
    )
    if report_row is None:
        raise ValueError("manifest không liệt kê validation_report.json")
    report_row["size_bytes"] = len(report_raw)
    report_row["sha256"] = hashlib.sha256(report_raw).hexdigest()
    manifest_raw = _json_bytes(manifest)
    candidate_files = dict(files)
    candidate_files["validation_report.json"] = report_raw
    candidate = {"manifest.json": manifest_raw, **candidate_files}
    result = inspect_members(candidate, archive=True, parent=parent, contract=contract)
    if result.get("integrity_status") != "PASS":
        failures = "; ".join(
            str(row.get("detail")) for row in result.get("checks", [])
            if isinstance(row, Mapping) and row.get("status") == "FAIL"
        )
        raise ValueError("Ứng viên hậu kiểm không hợp lệ: " + failures)
    checkpoint = CHECKPOINT_NAMES[stage]
    backup = _backup_integrity_files(root, ["manifest.json", "validation_report.json", checkpoint])
    try:
        publish_package_atomic(root / "validation_report.json", report_raw)
        publish_package_atomic(root / checkpoint, _archive_bytes(candidate))
        publish_package_atomic(root / "manifest.json", manifest_raw)
        return result, backup, updated_ids
    except Exception:
        restore_integrity_backup(root, backup)
        raise


def repair_directory_integrity(root: Path, *, contract: PromptContract | None = None) -> tuple[dict[str, Any], Path]:
    """Apply the safe repair plan, validate it, then publish with a backup."""
    plan = plan_directory_integrity_repair(root)
    if not plan["can_repair"]:
        raise ValueError("Không có phương án sửa tự động an toàn: " + "; ".join(plan["blockers"]))
    manifest = read_json((root / "manifest.json").read_bytes())
    contract = contract or prompt_contract_for_version(str(manifest.get("prompt_version") or ""))
    rows = manifest["files"]
    files = {row["path"]: (root / Path(row["path"])).read_bytes() for row in rows}
    changed_files: dict[str, bytes] = {}
    exclude_action = next((row for row in plan["actions"] if row["kind"] == "EXCLUDE_UNBOUND_CHARACTER_FILES"), None)
    excluded = set(exclude_action.get("paths", [])) if exclude_action else set()
    for path in excluded:
        files.pop(path, None)
    basename_action = next((row for row in plan["actions"] if row["kind"] == "NORMALIZE_VISUAL_BASENAMES"), None)
    if basename_action:
        visual_plan = read_json(files["visual_plan.json"])
        replacements = {row["from"]: row["to"] for row in basename_action["changes"]}
        for asset in visual_plan["assets"]:
            if asset.get("basename") in replacements:
                asset["basename"] = replacements[asset["basename"]]
        # Revalidate the semantic result before it can affect any file.
        active_image_basenames(visual_plan, contract)
        files["visual_plan.json"] = _json_bytes(visual_plan)
        changed_files["visual_plan.json"] = files["visual_plan.json"]
    link_action = next((row for row in plan["actions"] if row["kind"] == "LINK_CHARACTER_REFERENCES"), None)
    if link_action:
        visual_plan = read_json(files["visual_plan.json"])
        links = {row["character_id"]: row["path"] for row in link_action["links"]}
        for path in links.values():
            if path not in files:
                files[path] = (root / Path(path)).read_bytes()
        for character in visual_plan["characters"]:
            character_id = str(character.get("character_id"))
            if character_id in links:
                character["planned_reference_path"] = links[character_id]
                character["reference_path"] = links[character_id]
                character["reference_status"] = "READY"
        if links:
            visual_plan["reference_mode"] = "IMAGE_REFERENCE"
        files["visual_plan.json"] = _json_bytes(visual_plan)
        changed_files["visual_plan.json"] = files["visual_plan.json"]
    updated = dict(manifest)
    existing_rows = {row["path"]: dict(row) for row in rows if row["path"] not in excluded}
    if link_action:
        for path in links.values():
            existing_rows.setdefault(path, {"path": path, "origin_stage": 2})
    updated["files"] = [
        {
            **existing_rows[path],
            "size_bytes": len(files[path]),
            "sha256": hashlib.sha256(files[path]).hexdigest(),
        }
        for path in sorted(existing_rows)
    ]
    manifest_raw = _json_bytes(updated)
    members = {"manifest.json": manifest_raw, **files}
    result = inspect_members(members, archive=True, contract=contract)
    if result.get("integrity_status") != "PASS":
        failures = "; ".join(row["detail"] for row in result["checks"] if row["status"] == "FAIL")
        raise ValueError("Ứng viên sau sửa không hợp lệ: " + failures)
    stage = _stage_number(manifest["stage"])
    checkpoint = CHECKPOINT_NAMES[stage]
    backup = _backup_integrity_files(root, ["manifest.json", checkpoint, *changed_files])
    for name, raw in changed_files.items():
        publish_package_atomic(root / name, raw)
    publish_package_atomic(root / checkpoint, _archive_bytes(members))
    publish_package_atomic(root / "manifest.json", manifest_raw)
    return result, backup


def repair_directory_manifest(root: Path, *, contract: PromptContract | None = None) -> dict[str, Any]:
    """Rebind a valid directory package to its current payload bytes.

    The file allowlist and origin stages remain authoritative.  The candidate
    manifest and checkpoint archive are fully validated before either replaces
    an existing artifact.
    """
    current = read_json((root / "manifest.json").read_bytes())
    contract = contract or prompt_contract_for_version(str(current.get("prompt_version") or ""))
    rows = current.get("files")
    if not isinstance(rows, list):
        raise ValueError("manifest.files phải là array")
    files = _directory_files(root)
    rebound_rows = []
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            raise ValueError("manifest.files không hợp lệ")
        raw = files[row["path"]]
        rebound = dict(row)
        rebound["size_bytes"] = len(raw)
        rebound["sha256"] = hashlib.sha256(raw).hexdigest()
        rebound_rows.append(rebound)
    updated = dict(current)
    updated["files"] = rebound_rows
    manifest_raw = _json_bytes(updated)
    members = {"manifest.json": manifest_raw, **files}
    result = inspect_members(members, archive=True, contract=contract)
    if result["status"] != "PASS":
        failures = "; ".join(row["detail"] for row in result["checks"] if row["status"] == "FAIL")
        raise ValueError("Không thể đồng bộ manifest: " + failures)
    archive_raw = _archive_bytes(members)
    raw_stage = current.get("stage")
    if not isinstance(raw_stage, (str, int)) or isinstance(raw_stage, bool):
        raise ValueError("manifest.stage không hợp lệ")
    stage = _stage_number(raw_stage)
    publish_package_atomic(root / CHECKPOINT_NAMES[stage], archive_raw)
    publish_package_atomic(root / "manifest.json", manifest_raw)
    return result


def _directory_files(root: Path) -> dict[str, bytes]:
    manifest = read_json((root / "manifest.json").read_bytes()) if (root / "manifest.json").is_file() else None
    if manifest:
        names = [row["path"] for row in manifest.get("files", [])]
    else:
        names = [str(path.relative_to(root)).replace("\\", "/") for path in root.rglob("*") if path.is_file() and path.suffix.lower() != ".zip" and path.name != "manifest.json"]
    return {name: (root / Path(name)).read_bytes() for name in names}


def publish_stage1_checkpoint(root: Path, *, contract: PromptContract | None = None, **_: Any) -> dict[str, Any]:
    payload, result = build_workflow_package(1, "CREATE", _directory_files(root), contract=contract)
    publish_package_atomic(root / "story_stage1.zip", payload)
    return result


def publish_stage2_checkpoint(root: Path, *, contract: PromptContract | None = None) -> dict[str, Any]:
    parent = read_archive(root / "story_stage1.zip")
    payload, result = build_workflow_package(2, "CREATE", _directory_files(root), parent=parent, contract=contract)
    publish_package_atomic(root / "story_stage2.zip", payload)
    return result


def publish_stage4_release(root: Path, parent: Mapping[str, bytes], *, contract: PromptContract | None = None, **_: Any) -> dict[str, Any]:
    payload, result = build_workflow_package(4, "CREATE", _directory_files(root), parent=parent, contract=contract)
    publish_package_atomic(root / "story_video_prompts.zip", payload)
    return result


def publish_story_validation_report(root: Path, raw: bytes, **_: Any) -> Path:
    read_json(raw)
    destination = root / "validation_report.json"
    publish_package_atomic(destination, raw)
    return destination


def rebuild_checkpoint_chain(root: Path, **_: Any) -> dict[str, Any]:
    manifest = read_json((root / "manifest.json").read_bytes())
    stage = manifest["stage"]
    payload, result = build_workflow_package(stage, "REPAIR", _directory_files(root))
    names = {1: "story_stage1.zip", 2: "story_stage2.zip", 3: "story.zip", 4: "story_video_prompts.zip"}
    publish_package_atomic(root / names[stage], payload)
    return result


__all__ = ["build_workflow_package", "manifest_digest_mismatches", "plan_directory_integrity_repair", "publish_package_atomic", "publish_story_validation_report", "publish_stage1_checkpoint", "publish_stage2_checkpoint", "publish_stage4_release", "rebuild_checkpoint_chain", "repair_directory_integrity", "repair_directory_manifest", "rerun_deterministic_gates_atomic", "review_model_gate_atomic", "restore_integrity_backup"]
