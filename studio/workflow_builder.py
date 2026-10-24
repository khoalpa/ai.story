"""Deterministic package writer for the v4.1.6 four-stage format."""
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

from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.workflow_package import (
    FILE_FIELDS,
    inspect_members,
    read_archive,
    read_json,
)


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


__all__ = ["build_workflow_package", "publish_package_atomic", "publish_story_validation_report", "publish_stage1_checkpoint", "publish_stage2_checkpoint", "publish_stage4_release", "rebuild_checkpoint_chain"]
