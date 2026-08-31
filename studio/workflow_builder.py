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

from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.workflow_package import (
    FILE_FIELDS,
    MANIFEST_FIELDS,
    VALIDATION_FIELDS,
    expected_files,
    inspect_members,
    owner_stage,
    package_digest,
    read_json,
)


def _json_bytes(value: Any) -> bytes:
    text = unicodedata.normalize("NFC", json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return text.encode("utf-8")


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
    story = read_json(files["story.json"])
    expected = expected_files(stage, story, "series_anchor.json" in files, contract)[1:]
    if list(files) != expected:
        raise ValueError("Input files phải đúng exact allowlist và canonical order của stage")
    if stage == stages[0] and operation == "CREATE":
        if parent is not None:
            raise ValueError("Stage 1 CREATE không nhận parent")
        parent_digest = None
    else:
        if parent is None:
            raise ValueError("Stage sau hoặc REPAIR bắt buộc có exact parent package")
        prior = inspect_members(parent, archive=True, contract=contract)
        wanted = stage if operation == "REPAIR" else stages[index - 1]
        if prior.get("integrity_status") != "PASS" or prior.get("stage") != wanted:
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
        contract.version_label, read_json(files["story_validation.json"]).get("active_profile"),
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


__all__ = ["build_workflow_package", "publish_package_atomic"]
