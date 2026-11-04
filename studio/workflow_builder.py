"""Deterministic package writer for the v4.1.6 four-stage format."""
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
from typing import Any, Mapping

from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.workflow_package import (
    FILE_FIELDS,
    _expected_payload,
    inspect_members,
    read_archive,
    read_json,
)

CHECKPOINT_NAMES = {1: "story_stage1.zip", 2: "story_stage2.zip", 3: "story.zip", 4: "story_video_prompts.zip"}


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


def _stage_number(stage: str | int) -> int:
    if type(stage) is int and stage in range(1, 5):
        return stage
    if isinstance(stage, str) and stage in {f"STAGE{i}" for i in range(1, 5)}:
        return int(stage[-1])
    raise ValueError("Stage phải là 1..4 hoặc STAGE1..STAGE4")


def _origin_stage(path: str, stage: int, parent_manifest: Mapping[str, Any] | None) -> int:
    if parent_manifest:
        for row in parent_manifest.get("files", []):
            if isinstance(row, Mapping) and row.get("path") == path:
                return int(row["origin_stage"])
    if path in {"story.json"} or path == "series_anchor.json":
        return 1
    if path.startswith(("characters/", "landscape/")) or path in {"visual_plan.json", "visual_bible.txt"}:
        return 2
    if path.startswith("portrait/"):
        return 3
    return stage


def build_workflow_package(stage: str | int, operation: str, files: Mapping[str, bytes], *,
                           parent: Mapping[str, bytes] | None = None,
                           contract: PromptContract | None = None) -> tuple[bytes, dict[str, Any]]:
    contract = contract or load_prompt_contract()
    number = _stage_number(stage)
    if operation not in {"CREATE", "REPAIR"}:
        raise ValueError("operation phải là CREATE hoặc REPAIR")
    if "manifest.json" in files:
        raise ValueError("Builder tự tạo manifest.json")
    if not {"story.json", "validation_report.json"}.issubset(files):
        raise ValueError("Thiếu story.json hoặc validation_report.json")
    for name, raw in files.items():
        if name.endswith(".json") and read_json(raw).get("schema_version") != "4.1.3":
            raise ValueError(f"{name} không dùng schema 4.1.3")
    report = read_json(files["validation_report.json"])
    if report.get("prompt_version") != "4.1.6" or report.get("stage") != number:
        raise ValueError("validation_report không khớp prompt/stage v4.1.6")
    parent_manifest = read_json(parent["manifest.json"]) if parent and "manifest.json" in parent else None
    parent_sha = hashlib.sha256(_archive_bytes(parent)).hexdigest() if parent else None
    rows = []
    for name in sorted(files):
        raw = files[name]
        rows.append(dict(zip(FILE_FIELDS, (name, len(raw), hashlib.sha256(raw).hexdigest(), _origin_stage(name, number, parent_manifest)))))
    manifest = {"schema_version": "4.1.3", "prompt_version": "4.1.6", "stage": number,
                "status": report.get("status"), "parent_package_sha256": parent_sha, "files": rows}
    members = {"manifest.json": _json_bytes(manifest), **files}
    payload = _archive_bytes(members)
    inspection = inspect_members(read_archive(payload), archive=True, parent=parent, contract=contract)
    if inspection["status"] != "PASS":
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
            expected = _expected_payload({"manifest.json": (root / "manifest.json").read_bytes(), **members}, int(manifest["stage"]))
            extras = sorted(listed - expected)
            visual_plan = read_json(members["visual_plan.json"])
            characters = visual_plan.get("characters")
            by_id = {
                str(row.get("character_id")): row for row in characters
                if isinstance(row, Mapping) and row.get("character_id")
            } if isinstance(characters, list) else {}
            linkable: list[dict[str, str]] = []
            unresolved: list[str] = []
            linked_ids: set[str] = set()
            for path in extras:
                candidate = Path(path)
                character_id = candidate.stem
                row = by_id.get(character_id)
                if candidate.parent.as_posix() == "characters" and candidate.suffix.lower() == ".png" and row is not None:
                    linkable.append({"character_id": character_id, "path": path})
                    linked_ids.add(character_id)
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
                actions.append({"kind": "LINK_CHARACTER_REFERENCES", "detail": f"Liên kết {len(linkable)} ảnh với nhân vật cùng ID trong visual_plan.json.", "links": linkable})
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


def repair_directory_integrity(root: Path, *, contract: PromptContract | None = None) -> tuple[dict[str, Any], Path]:
    """Apply the safe repair plan, validate it, then publish with a backup."""
    contract = contract or load_prompt_contract()
    plan = plan_directory_integrity_repair(root)
    if not plan["can_repair"]:
        raise ValueError("Không có phương án sửa tự động an toàn: " + "; ".join(plan["blockers"]))
    manifest = read_json((root / "manifest.json").read_bytes())
    rows = manifest["files"]
    files = {row["path"]: (root / Path(row["path"])).read_bytes() for row in rows}
    changed_files: dict[str, bytes] = {}
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
    existing_rows = {row["path"]: dict(row) for row in rows}
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
    if result["status"] != "PASS":
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
    contract = contract or load_prompt_contract()
    current = read_json((root / "manifest.json").read_bytes())
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


__all__ = ["build_workflow_package", "manifest_digest_mismatches", "plan_directory_integrity_repair", "publish_package_atomic", "publish_story_validation_report", "publish_stage1_checkpoint", "publish_stage2_checkpoint", "publish_stage4_release", "rebuild_checkpoint_chain", "repair_directory_integrity", "repair_directory_manifest", "restore_integrity_backup"]
