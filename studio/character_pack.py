"""Character Image Pack v1.0 contract, deterministic builder and Stage 2 linker."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zipfile
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.artifact_validation import strict_json_bytes
from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.workflow_builder import build_workflow_package
from studio.workflow_package import read_archive

PACK_VERSION = "1.0"
PROMPT_VERSION = "4.2.0"
SCOPE = "CHARACTER_IMAGE_PACK"
VIEWS = ("FRONT", "SIDE", "BACK", "EXPRESSIONS")
VIEW_FILES = {view: view.casefold() + ".png" for view in VIEWS}
SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
DIGEST = re.compile(r"[0-9a-f]{64}")
PACK_FIELDS = {"character_pack_version", "prompt_version", "source", "style_lock", "characters"}
REPORT_FIELDS = {"character_pack_version", "prompt_version", "scope", "status", "input_sources", "checks", "limitations", "remaining_work", "archive_validation"}
MANIFEST_FIELDS = {"character_pack_version", "prompt_version", "scope", "status", "files"}
IMAGE_FIELDS = {"planned_path", "path", "status"}
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_PACKAGE_BYTES = 512 * 1024 * 1024


def _json(raw: bytes) -> dict[str, Any]:
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("JSON vượt giới hạn 5 MiB")
    return dict(strict_json_bytes(raw))


def _json_bytes(value: Any) -> bytes:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return unicodedata.normalize("NFC", text).encode("utf-8")


def _safe_path(name: object) -> bool:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _archive_bytes(members: Mapping[str, bytes]) -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, members[name])
    return stream.getvalue()


def read_character_pack(source: bytes | bytearray | str | Any) -> dict[str, bytes]:
    """Read a CIP archive with path, duplicate, size and CRC checks."""
    raw = bytes(source) if isinstance(source, (bytes, bytearray)) else None
    if raw is not None and len(raw) > MAX_PACKAGE_BYTES:
        raise ValueError("Character Image Pack vượt giới hạn 512 MiB")
    archive_source: Any = BytesIO(raw) if raw is not None else source
    with zipfile.ZipFile(archive_source) as archive:
        members: dict[str, bytes] = {}
        folded: set[str] = set()
        total = 0
        for info in archive.infolist():
            name = info.filename
            if info.is_dir():
                continue
            if not _safe_path(name) or name.casefold() in folded:
                raise ValueError(f"Đường dẫn CIP không an toàn hoặc trùng: {name}")
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError(f"Tệp CIP vượt giới hạn: {name}")
            folded.add(name.casefold())
            total += info.file_size
            if total > MAX_PACKAGE_BYTES:
                raise ValueError("Payload Character Image Pack vượt giới hạn")
            members[name] = archive.read(info)
        if archive.testzip() is not None:
            raise ValueError("CRC Character Image Pack không hợp lệ")
    return members


def inspect_character_pack(members: Mapping[str, bytes], *, archive: bool = False) -> dict[str, Any]:
    """Validate closed metadata schemas, inventory, digests and final PNG bytes."""
    checks: list[dict[str, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detector_class": "DETERMINISTIC", "detail": detail})

    required_metadata = {"character_pack.json", "character_style_bible.txt", "character_pack_report.json", "character_pack_manifest.json"}
    safe = all(_safe_path(name) for name in members) and len({name.casefold() for name in members}) == len(members)
    check("safe_paths", safe, "Đường dẫn payload an toàn và duy nhất." if safe else "Có đường dẫn không an toàn hoặc trùng.")
    check("metadata_files", required_metadata <= set(members), "Đủ metadata CIP." if required_metadata <= set(members) else "Thiếu metadata CIP bắt buộc.")
    try:
        pack = _json(members["character_pack.json"])
        report = _json(members["character_pack_report.json"])
        manifest = _json(members["character_pack_manifest.json"])
    except (KeyError, ValueError, UnicodeError) as exc:
        check("metadata_schema", False, f"Metadata CIP không hợp lệ: {exc}")
        return {"status": "FAIL", "compatibility": "UNSUPPORTED", "checks": checks, "pack": {}, "report": {}, "manifest": {}, "files": []}

    source = pack.get("source")
    source_ok = bool(isinstance(source, Mapping) and set(source) == {"kind", "identifier", "sha256"} and source.get("kind") in {"STORY_JSON", "USER_BRIEF", "USER_IMAGES"} and (source.get("identifier") is None or isinstance(source.get("identifier"), str)) and (source.get("sha256") is None or isinstance(source.get("sha256"), str) and DIGEST.fullmatch(source["sha256"])))
    chars = pack.get("characters")
    chars_ok = isinstance(chars, list) and bool(chars)
    expected_images: set[str] = set()
    safe_ids: set[str] = set()
    ready_paths: set[str] = set()
    if isinstance(chars, list):
        for row in chars:
            valid = isinstance(row, Mapping) and set(row) == {"source_character_id", "safe_id", "name", "character_lock", "images"}
            safe_id = row.get("safe_id") if isinstance(row, Mapping) else None
            valid = bool(valid and isinstance(safe_id, str) and SAFE_ID.fullmatch(safe_id) and safe_id not in safe_ids and isinstance(row.get("name"), str) and row["name"].strip() and isinstance(row.get("character_lock"), str) and row["character_lock"].strip())
            if valid and isinstance(safe_id, str):
                safe_ids.add(safe_id)
                images = row.get("images")
                valid = isinstance(images, Mapping) and tuple(images) == VIEWS
                if valid:
                    for view in VIEWS:
                        image = images[view]
                        planned = f"characters/{safe_id}/{VIEW_FILES[view]}"
                        image_ok = isinstance(image, Mapping) and set(image) == IMAGE_FIELDS and image.get("planned_path") == planned and image.get("status") in {"PENDING", "READY", "FAILED"}
                        if image_ok and image.get("status") == "READY":
                            image_ok = image.get("path") == planned
                            ready_paths.add(planned)
                        elif image_ok:
                            image_ok = image.get("path") is None
                        valid = bool(valid and image_ok)
                        expected_images.add(planned)
            chars_ok = bool(chars_ok and valid)
    pack_ok = set(pack) == PACK_FIELDS and pack.get("character_pack_version") == PACK_VERSION and pack.get("prompt_version") == PROMPT_VERSION and isinstance(pack.get("style_lock"), str) and bool(pack["style_lock"].strip()) and source_ok and chars_ok

    status_values = {"COMPLETE", "PARTIAL", "BLOCKED"}
    report_ok = set(report) == REPORT_FIELDS and report.get("character_pack_version") == PACK_VERSION and report.get("prompt_version") == PROMPT_VERSION and report.get("scope") == SCOPE and report.get("status") in status_values and all(isinstance(report.get(key), list) for key in ("input_sources", "checks", "limitations", "remaining_work")) and isinstance(report.get("archive_validation"), Mapping)
    rows = manifest.get("files")
    manifest_ok = set(manifest) == MANIFEST_FIELDS and manifest.get("character_pack_version") == PACK_VERSION and manifest.get("prompt_version") == PROMPT_VERSION and manifest.get("scope") == SCOPE and manifest.get("status") == report.get("status") and isinstance(rows, list)
    indexed: dict[str, Mapping[str, Any]] = {}
    if isinstance(rows, list):
        paths: list[str] = []
        for row in rows:
            valid = bool(isinstance(row, Mapping) and set(row) == {"path", "size_bytes", "sha256"} and _safe_path(row.get("path")) and type(row.get("size_bytes")) is int and row["size_bytes"] >= 0 and (row.get("sha256") is None or isinstance(row.get("sha256"), str) and DIGEST.fullmatch(row["sha256"])))
            if not valid:
                manifest_ok = False
                break
            paths.append(row["path"])
            indexed[row["path"]] = row
        manifest_ok = bool(manifest_ok and paths == sorted(paths) and len(paths) == len(set(path.casefold() for path in paths)))
    metadata_ok = bool(pack_ok and report_ok and manifest_ok)
    check("metadata_schema", metadata_ok, "Closed schema CIP hợp lệ." if metadata_ok else "Closed schema CIP không hợp lệ.")

    actual = set(members) - {"character_pack_manifest.json"}
    inventory_ok = set(indexed) == actual and ready_paths <= actual and not ((expected_images - ready_paths) & actual)
    check("file_inventory", inventory_ok, "Manifest và trạng thái ảnh khớp payload." if inventory_ok else "Manifest, planned paths hoặc payload ảnh không khớp.")
    digest_ok = inventory_ok
    for path, row in indexed.items():
        raw = members.get(path)
        digest_ok = bool(digest_ok and raw is not None and len(raw) == row["size_bytes"] and (row.get("sha256") is None or hashlib.sha256(raw).hexdigest() == row["sha256"]))
    check("file_digest", digest_ok, "Size/hash payload khớp." if digest_ok else "Size/hash payload không khớp.")

    png_ok = True
    for path in ready_paths:
        try:
            with Image.open(BytesIO(members[path])) as image:
                image.load()
                png_ok = png_ok and image.format == "PNG" and image.width > 0 and image.height > 0
        except (KeyError, OSError, UnidentifiedImageError):
            png_ok = False
    check("image_files", png_ok, "Mọi ảnh READY là PNG giải mã được." if png_ok else "Có ảnh READY không phải PNG hợp lệ.")
    complete_ok = report.get("status") != "COMPLETE" or ready_paths == expected_images
    check("completion", complete_ok, "Trạng thái hoàn tất nhất quán." if complete_ok else "COMPLETE nhưng chưa đủ bốn ảnh mỗi nhân vật.")
    success = all(row["status"] == "PASS" for row in checks)
    return {"status": "PASS" if success else "FAIL", "compatibility": "NATIVE_CURRENT" if pack_ok else "UNSUPPORTED", "checks": checks, "pack": pack, "report": report, "manifest": manifest, "files": [dict(indexed[path]) for path in sorted(indexed)], "archive": archive}


def build_character_pack(pack: Mapping[str, Any], style_bible: str, images: Mapping[str, bytes], report: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Build a deterministic CIP archive; semantic review evidence remains caller supplied."""
    if not style_bible.strip():
        raise ValueError("character_style_bible.txt không được rỗng")
    files = {"character_pack.json": _json_bytes(pack), "character_style_bible.txt": style_bible.encode("utf-8"), "character_pack_report.json": _json_bytes(report), **dict(images)}
    rows = [{"path": path, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for path, raw in sorted(files.items())]
    manifest = {"character_pack_version": PACK_VERSION, "prompt_version": PROMPT_VERSION, "scope": SCOPE, "status": report.get("status"), "files": rows}
    members = {**files, "character_pack_manifest.json": _json_bytes(manifest)}
    payload = _archive_bytes(members)
    reopened = read_character_pack(payload)
    inspection = inspect_character_pack(reopened, archive=True)
    if inspection["status"] != "PASS":
        failures = "; ".join(row["detail"] for row in inspection["checks"] if row["status"] == "FAIL")
        raise ValueError("Character Image Pack không hợp lệ: " + failures)
    return payload, inspection


def link_character_pack_to_stage2(stage2: bytes | Mapping[str, bytes], character_pack: bytes | Mapping[str, bytes], mappings: Mapping[str, str], *, contract: PromptContract | None = None) -> tuple[bytes, dict[str, Any]]:
    """Create a PARTIAL Stage 2 repair snapshot using reviewed CIP FRONT bytes.

    ``mappings`` maps Stage 2 ``character_id`` to CIP ``source_character_id``.
    Existing snapshots are never mutated and downstream visual gates are reset.
    """
    contract = contract or load_prompt_contract()
    if contract.version_label != PROMPT_VERSION:
        raise ValueError("Liên kết Character Image Pack yêu cầu contract prompt 4.2.0")
    stage_members = dict(stage2) if isinstance(stage2, Mapping) else read_archive(stage2)
    cip_members = dict(character_pack) if isinstance(character_pack, Mapping) else read_character_pack(character_pack)
    cip_result = inspect_character_pack(cip_members, archive=True)
    if cip_result["status"] != "PASS":
        raise ValueError("Character Image Pack chưa vượt kiểm tra deterministic")
    stage_manifest = _json(stage_members["manifest.json"])
    if stage_manifest.get("stage") != 2:
        raise ValueError("Chỉ liên kết vào snapshot Stage 2")
    plan = _json(stage_members["visual_plan.json"])
    by_source = {row.get("source_character_id"): row for row in cip_result["pack"]["characters"]}
    characters = plan.get("characters")
    if not isinstance(characters, list):
        raise ValueError("visual_plan.characters không hợp lệ")
    files = {name: raw for name, raw in stage_members.items() if name != "manifest.json"}
    linked: list[str] = []
    for row in characters:
        if not isinstance(row, dict) or row.get("character_id") not in mappings:
            continue
        character_id = str(row["character_id"])
        source_id = mappings[character_id]
        source = by_source.get(source_id)
        if source is None:
            raise ValueError(f"Không tìm thấy source_character_id {source_id!r} trong CIP")
        front = source["images"]["FRONT"]
        if front.get("status") != "READY" or not isinstance(front.get("path"), str):
            raise ValueError(f"Ảnh FRONT của {source_id!r} chưa READY")
        target = f"characters/{character_id}.png"
        files[target] = cip_members[front["path"]]
        row["planned_reference_path"] = target
        row["reference_path"] = target
        row["reference_status"] = "READY"
        linked.append(character_id)
    if set(mappings) != set(linked):
        raise ValueError("Có character_id ánh xạ không tồn tại trong visual_plan.json")
    plan["reference_mode"] = "IMAGE_REFERENCE"
    files["visual_plan.json"] = _json_bytes(plan)
    report = _json(files["validation_report.json"])
    report["prompt_version"] = PROMPT_VERSION
    report["status"] = "PARTIAL"
    report["input_sources"] = [*report.get("input_sources", []), "Character Image Pack | prompt_version=4.2.0 | linked_front_ids=" + ",".join(sorted(linked))]
    report["limitations"] = [*report.get("limitations", []), "Ảnh tham chiếu FRONT đã thay đổi; cần nhìn soát lại ảnh ngang và các artifact phụ thuộc."]
    report["remaining_work"] = [*report.get("remaining_work", []), "Chạy lại CHARACTER_IDENTITY, IMAGE_FILES và các gate hình ảnh Stage 2 sau liên kết CIP."]
    for check in report.get("checks", []):
        if isinstance(check, dict) and check.get("id") in {"CHARACTER_IDENTITY", "IMAGE_FILES", "CONTINUITY", "VISUAL_PARITY"}:
            check["status"] = "NOT_VERIFIED"
            check["details"] = "Đã reset do liên kết Character Image Pack."
    files["validation_report.json"] = _json_bytes(report)
    payload, inspection = build_workflow_package(2, "REPAIR", files, parent=stage_members, contract=contract)
    return payload, {**inspection, "linked_character_ids": sorted(linked), "requires_visual_review": True}


def render_character_pack_workspace() -> None:
    """Render CIP inspection and explicit Stage 2 linking controls."""
    import streamlit as st

    st.caption("CIP là artifact độc lập, không phải Stage 5. Việc tải pack lên không tự sửa gói truyện.")
    uploaded = st.file_uploader("Character Image Pack", type=["zip"], key="character_pack_upload")
    if uploaded is None:
        st.info("Tải character_image_pack.zip để kiểm metadata, inventory, digest và PNG.")
        return
    try:
        raw = uploaded.getvalue()
        members = read_character_pack(raw)
        result = inspect_character_pack(members, archive=True)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        st.error(str(exc))
        return
    (st.success if result["status"] == "PASS" else st.error)(f"Kiểm tra deterministic: {result['status']}")
    st.dataframe(result["checks"], hide_index=True, width="stretch")
    characters = result.get("pack", {}).get("characters", [])
    st.dataframe([
        {"source_character_id": row.get("source_character_id"), "safe_id": row.get("safe_id"),
         "name": row.get("name"), **{view: row.get("images", {}).get(view, {}).get("status") for view in VIEWS}}
        for row in characters if isinstance(row, Mapping)
    ], hide_index=True, width="stretch")
    stage_upload = st.file_uploader("Stage 2 ZIP để liên kết FRONT (tùy chọn)", type=["zip"], key="character_pack_stage2_upload")
    if stage_upload is None or result["status"] != "PASS":
        return
    try:
        stage_members = read_archive(stage_upload.getvalue())
        plan = _json(stage_members["visual_plan.json"])
        stage_ids = {str(value) for row in plan.get("characters", []) if isinstance(row, Mapping) and isinstance((value := row.get("character_id")), str)}
        source_ids = {str(value) for row in characters if isinstance(row, Mapping) and isinstance((value := row.get("source_character_id")), str)}
        exact = {value: value for value in sorted(stage_ids & source_ids)}
        if not exact:
            st.warning("Không có ID trùng chính xác; cần ánh xạ có chủ đích ngoài giao diện này.")
            return
        st.caption("Ánh xạ ID chính xác: " + ", ".join(exact))
        if st.button("Tạo repair snapshot Stage 2", type="primary", key="character_pack_link"):
            payload, linked = link_character_pack_to_stage2(stage_members, members, exact, contract=load_prompt_contract())
            st.session_state["character_pack_linked_payload"] = payload
            st.success(f"Đã tạo snapshot PARTIAL; cần review lại: {', '.join(linked['linked_character_ids'])}")
    except (KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
        st.error(str(exc))
    payload = st.session_state.get("character_pack_linked_payload")
    if isinstance(payload, bytes):
        st.download_button("Tải story_stage2_cip_repair.zip", payload, file_name="story_stage2_cip_repair.zip", mime="application/zip")


__all__ = [
    "PACK_VERSION", "PROMPT_VERSION", "SCOPE", "VIEWS", "build_character_pack",
    "inspect_character_pack", "link_character_pack_to_stage2", "read_character_pack",
    "render_character_pack_workspace",
]
