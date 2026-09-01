"""Read-only progressive package inspection. Never treats report claims as evidence."""
from __future__ import annotations

import hashlib
import json
import re
import stat
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from studio.artifact_validation import strict_json_bytes
from studio.prompt_contract import PromptContract, load_prompt_contract

WORKFLOW_FILES = {
    "workflow": "workflow_manifest.json",
    "visual_bible": "visual_bible.json",
    "video_prompts": "video_prompts.json",
}
STAGES = ("STAGE1", "STAGE2", "STAGE3", "STAGE4")
# Compatibility exports for callers that render fixed labels. Validation loads
# the selected prompt contract at call time and does not rely on these values.
PURPOSES = ("WORKFLOW_CHECKPOINT", "WORKFLOW_CHECKPOINT", "AUDIO_STORY_RELEASE", "VIDEO_PRODUCTION_RELEASE")
MANIFEST_FIELDS = tuple("schema_version package_stage package_purpose operation_mode created_by_prompt_version active_profile story_sha256 parent_package_digest_sha256 allowed_next_stage file_count files validation package_digest_sha256".split())
FILE_FIELDS = ("path", "sha256", "size_bytes", "owner_stage", "mutation_status")
VALIDATION_FIELDS = tuple("manifest_schema_status archive_security_status file_set_status file_digest_status stage_ownership_status parent_binding_status stage_gate_status status".split())
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 5 * 1024 * 1024
INTEGRITY_CHECKS = {"manifest_schema", "file_schema", "file_set", "file_digest", "package_digest",
                    "story_binding", "stage_ownership", "parent_binding", "archive_reopen", "strict_json"}


def read_json(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON vượt giới hạn 5 MiB")
    # The shared parser enforces UTF-8, finite numbers, and duplicate raw keys.
    document = strict_json_bytes(raw)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            keys = [unicodedata.normalize("NFC", k) for k in value]
            if len(keys) != len(set(keys)):
                raise ValueError("JSON có key trùng sau Unicode NFC")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(document)
    return dict(document)


def safe_name(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    return (not path.is_absolute() and path.as_posix() == name
            and all(part not in {".", ".."} and not part.endswith((".", " ")) for part in name.split("/"))
            and unicodedata.normalize("NFC", name) == name)


def read_archive(source: Path | bytes) -> dict[str, bytes]:
    """Bounded in-memory reopen, including CRC checks; never extracts user paths."""
    if (source.stat().st_size if isinstance(source, Path) else len(source)) > MAX_PACKAGE_BYTES:
        raise ValueError("ZIP vượt giới hạn 512 MiB")
    with zipfile.ZipFile(source if isinstance(source, Path) else BytesIO(source)) as archive:
        entries = archive.infolist()
        if len(entries) > 1024 or sum(item.file_size for item in entries) > MAX_PACKAGE_BYTES:
            raise ValueError("ZIP vượt giới hạn số file/dung lượng giải nén")
        seen: set[str] = set()
        for item in entries:
            name = item.filename
            mode = item.external_attr >> 16
            if (not safe_name(name) or item.orig_filename != name or not safe_name(item.orig_filename)
                    or name.casefold() in seen or item.is_dir()
                    or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                    or item.flag_bits & 1 or item.file_size > MAX_MEMBER_BYTES):
                raise ValueError(f"ZIP member không an toàn/trùng/không hỗ trợ: {name!r}")
            seen.add(name.casefold())
        return {item.filename: archive.read(item) for item in entries}


def _workflow_values(contract: PromptContract) -> tuple[tuple[str, ...], tuple[str, ...]]:
    stages = contract.workflow_package_stages or STAGES
    purposes = contract.workflow_package_purposes
    if len(stages) != 4 or len(purposes) != 3:
        raise ValueError("Prompt phải khai báo đúng 4 workflow stages và 3 package purposes")
    # The prompt defines Stage 1–2 as checkpoints and the last two as releases.
    return stages, (purposes[0], purposes[0], purposes[1], purposes[2])


def expected_files(stage: str, story: Mapping[str, Any], anchor: bool,
                   contract: PromptContract | None = None) -> list[str]:
    contract = contract or load_prompt_contract()
    stages, _ = _workflow_values(contract)
    if stage not in stages:
        raise ValueError("Stage phải lấy từ manifest hợp lệ")
    characters = story.get("characters")
    if not isinstance(characters, list) or not all(isinstance(c, dict) for c in characters):
        raise ValueError("story.characters phải là array object")
    ids = [c.get("character_id") for c in characters]
    if any(not isinstance(c, str) or not c or not safe_name(f"characters/{c}.png") or "/" in c for c in ids):
        raise ValueError("character_id không hợp lệ")
    if len(set(ids)) != len(ids):
        raise ValueError("character_id trùng")
    refs = [f"characters/{c}.png" for c in ids]
    names = contract.image_basenames
    landscape = [f"landscape/{n}" for n in names]
    portrait = [f"portrait/{n}" for n in names]
    base = ["story.json", "story_validation.json", *refs]
    if stage == stages[0]:
        files = base
    elif stage == stages[1]:
        files = [*base, "visual_bible.json", *landscape]
    else:
        files = [*landscape, *portrait, *base, "package_quality_report.json"]
        if stage == stages[3]:
            files.append(contract.video_prompt_file_name)
    return ["workflow_manifest.json", *files, *(["series_anchor.json"] if anchor else [])]


def owner_stage(name: str, contract: PromptContract | None = None) -> str:
    contract = contract or load_prompt_contract()
    stages, _ = _workflow_values(contract)
    if name.startswith("landscape/") or name == "visual_bible.json":
        return stages[1]
    if name.startswith("portrait/") or name == "package_quality_report.json":
        return stages[2]
    if name == contract.video_prompt_file_name:
        return stages[3]
    return stages[0]


def package_digest(rows: list[dict[str, Any]]) -> str:
    preimage = [{k: row[k] for k in ("path", "sha256", "size_bytes", "owner_stage")} for row in rows]
    raw = unicodedata.normalize("NFC", json.dumps(preimage, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def inspect_members(members: Mapping[str, bytes], *, archive: bool = False,
                    parent: Mapping[str, bytes] | None = None,
                    contract: PromptContract | None = None) -> dict[str, Any]:
    contract = contract or load_prompt_contract()
    stages, purposes = _workflow_values(contract)
    result: dict[str, Any] = {"stage": None, "purpose": None, "next_stage": None,
        "status": "NOT_VERIFIED", "checks": [], "files": [], "manifest": {},
        "compatibility": "NATIVE_CURRENT", "expected_count": None, "actual_count": len(members),
        "stage_gate_status": "NOT_VERIFIED", "integrity_status": "NOT_VERIFIED",
        "publish_status": "NOT_VERIFIED"}

    def check(name: str, passed: bool | None, detail: str) -> None:
        result["checks"].append({"check": name, "status": "NOT_VERIFIED" if passed is None else "PASS" if passed else "FAIL",
                                 "detector_class": "HOST_UNAVAILABLE" if passed is None else "DETERMINISTIC", "detail": detail})

    if "workflow_manifest.json" not in members:
        result["compatibility"] = "MIGRATION_REQUIRED"
        check("manifest", None, "Thiếu manifest: không suy stage; legacy cần adapter đúng phiên bản.")
        return result
    try:
        manifest = read_json(members["workflow_manifest.json"])
        result["manifest"] = manifest
        stage = manifest.get("package_stage")
        if stage not in stages:
            raise ValueError("package_stage không hợp lệ")
        index = stages.index(stage)
        result.update(stage=stage, purpose=purposes[index], next_stage=stages[index + 1] if index < 3 else None)
        validation = manifest.get("validation")
        operation = manifest.get("operation_mode")
        def hex_digest(value: Any) -> bool:
            return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        schema_ok = (tuple(manifest) == MANIFEST_FIELDS and manifest.get("schema_version") == contract.workflow_manifest_schema_version
            and manifest.get("package_purpose") == purposes[index]
            and operation in set(contract.workflow_operation_modes)
            and manifest.get("created_by_prompt_version") == contract.version_label
            and manifest.get("active_profile") in {"YOUTH_SAFE", "ADULT_STANDARD", "SERIAL_DETECTIVE"}
            and manifest.get("allowed_next_stage") == result["next_stage"]
            and type(manifest.get("file_count")) is int
            and hex_digest(manifest.get("story_sha256")) and hex_digest(manifest.get("package_digest_sha256"))
            and (manifest.get("parent_package_digest_sha256") is None if stage == stages[0] and operation == "CREATE"
                 else hex_digest(manifest.get("parent_package_digest_sha256")))
            and isinstance(validation, dict) and tuple(validation) == VALIDATION_FIELDS
            and all(value == "PASS" for value in validation.values()))
        check("manifest_schema", schema_ok, "Exact field/order/enum; Stage 2 purpose canonical = WORKFLOW_CHECKPOINT.")
        story = read_json(members["story.json"])
        rows = manifest.get("files")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("manifest.files phải là array object")
        rows_ok = all(tuple(r) == FILE_FIELDS and safe_name(r.get("path")) and hex_digest(r.get("sha256"))
            and type(r.get("size_bytes")) is int and r["size_bytes"] >= 0 and r.get("owner_stage") in stages
            and r.get("mutation_status") in set(contract.workflow_mutation_statuses) for r in rows)
        check("file_schema", rows_ok, "Exact member field/order/type và canonical path.")
        if not rows_ok:
            raise ValueError("Không thể xác minh member record sai schema")
        expected = expected_files(stage, story, "series_anchor.json" in members, contract)
        result["expected_count"] = len(expected)
        check("file_set", list(r["path"] for r in rows) == expected[1:]
              and set(members) == set(expected) and manifest.get("file_count") == len(expected)
              and len(rows) + 1 == len(expected) and (not archive or list(members) == expected),
              "Exact allowlist/order/count của stage, gồm optional anchor.")
        actual_rows = []
        for row in rows:
            raw = members.get(row["path"])
            digest = hashlib.sha256(raw).hexdigest() if raw is not None else None
            matches = raw is not None and len(raw) == row["size_bytes"] and digest == row["sha256"]
            result["files"].append({**row, "status": "PASS" if matches else "FAIL"})
            actual_rows.append({**row, "sha256": digest, "size_bytes": len(raw) if raw is not None else -1})
        check("file_digest", all(r["status"] == "PASS" for r in result["files"]), "SHA-256 và size được tính lại trên bytes đang đọc.")
        check("package_digest", package_digest(actual_rows) == manifest.get("package_digest_sha256"), "Canonical ordered member tuples; không hash ZIP container.")
        documents = {name: read_json(raw) for name, raw in members.items() if name.endswith(".json")}
        check("strict_json", True, "Mọi JSON trong gói được parse strict UTF-8, finite number, duplicate key/NFC.")
        profile = documents["story_validation.json"].get("active_profile")
        check("story_binding", hashlib.sha256(members["story.json"]).hexdigest() == manifest.get("story_sha256")
              and profile == manifest.get("active_profile"), "Exact story bytes và active_profile trong kiểm định.")
        check("stage_ownership", all(r["owner_stage"] == owner_stage(r["path"], contract)
              and (r["mutation_status"] == "READ_ONLY" if r["owner_stage"] != stage
                   else operation == "REPAIR" or r["mutation_status"] == "CREATED_CURRENT_STAGE") for r in rows),
              "Owner stage và mutation status của từng member.")
        if stage == stages[0] and operation == "CREATE":
            check("parent_binding", manifest.get("parent_package_digest_sha256") is None, "Stage 1 CREATE không có parent.")
        elif not manifest.get("parent_package_digest_sha256"):
            check("parent_binding", False, "Stage sau/REPAIR bắt buộc có parent digest.")
        elif parent is None:
            check("parent_binding", None, "Cần exact gói nguồn để kiểm tra parent digest và bytes kế thừa.")
        else:
            prior = inspect_members(parent, archive=True, contract=contract)
            prior_manifest = prior["manifest"]
            prior_checks = [c for c in prior["checks"] if c["check"] in INTEGRITY_CHECKS - {"parent_binding"}]
            prior_ok = (prior["status"] != "FAIL" and {c["check"] for c in prior_checks} == INTEGRITY_CHECKS - {"parent_binding"}
                        and all(c["status"] == "PASS" for c in prior_checks))
            wanted_stage = stage if operation == "REPAIR" else stages[index - 1]
            inherited = [r["path"] for r in rows if r["owner_stage"] != stage or r["mutation_status"] == "READ_ONLY"]
            anchor_preserved = stage not in {stages[1], stages[3]} or ("series_anchor.json" in members) == ("series_anchor.json" in parent)
            check("parent_binding", prior_ok and prior["stage"] == wanted_stage
                  and prior_manifest.get("package_digest_sha256") == manifest.get("parent_package_digest_sha256")
                  and all(members.get(n) == parent.get(n) for n in inherited) and anchor_preserved,
                  "Đối chiếu gói cha trực tiếp và bytes kế thừa; không chứng minh toàn bộ lịch sử tổ tiên.")
        check("archive_reopen", True if archive else None,
              "Đã đọc lại mọi ZIP member và CRC." if archive else "Đang xem thư mục; cần mở ZIP để kiểm CRC/duplicate entries.")
        reports_to_check = [documents["story_validation.json"]]
        if stage in {stages[2], stages[3]}:
            reports_to_check.append(documents.get("package_quality_report.json", {}))
        if stage == stages[3]:
            reports_to_check.append(documents.get(contract.video_prompt_file_name, {}))
        declared_failure = False
        for report in reports_to_check:
            report_validation = report.get("validation")
            summary = report.get("summary")
            if isinstance(report_validation, dict) and report_validation.get("status") == "FAIL":
                declared_failure = True
            if isinstance(summary, dict) and summary.get("publish_verdict") == "FAIL":
                declared_failure = True
            if isinstance(report.get("gates"), list):
                declared_failure |= any(isinstance(g, dict) and g.get("status") == "FAIL" and g.get("severity") != "ADVISORY" for g in report["gates"])
        if declared_failure:
            check("reported_blocker", False, "Artifact báo cáo có blocker FAIL; không thể xác nhận gói đạt.")
        check("stage_gate", None, "Chưa chạy đầy đủ detector safety/provenance/creative của stage; manifest PASS chỉ là khai báo.")
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        check("parse", False, str(exc))
    statuses = [c["status"] for c in result["checks"]]
    result["status"] = "FAIL" if "FAIL" in statuses else "NOT_VERIFIED" if "NOT_VERIFIED" in statuses else "PASS"
    integrity = [c["status"] for c in result["checks"] if c["check"] in INTEGRITY_CHECKS or c["check"] == "parse"]
    result["integrity_status"] = "FAIL" if "FAIL" in integrity else "NOT_VERIFIED" if "NOT_VERIFIED" in integrity else "PASS"
    stage_checks = [c["status"] for c in result["checks"] if c["check"] in {"stage_gate", "reported_blocker"}]
    result["stage_gate_status"] = "FAIL" if "FAIL" in stage_checks else "NOT_VERIFIED" if "NOT_VERIFIED" in stage_checks or not stage_checks else "PASS"
    result["publish_status"] = ("PASS" if result["integrity_status"] == result["stage_gate_status"] == "PASS"
                                else "FAIL" if "FAIL" in {result["integrity_status"], result["stage_gate_status"]}
                                else "NOT_VERIFIED")
    return result


def inspect_directory(root: Path, *, overridden: bool = False) -> dict[str, Any]:
    """Inspect only the package projection; production files stay outside it."""
    members: dict[str, bytes] = {}
    try:
        contract = load_prompt_contract()
        manifest_path = root / "workflow_manifest.json"
        if manifest_path.is_file():
            if not manifest_path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Manifest ngoài thư mục dự án")
            if manifest_path.stat().st_size > MAX_JSON_BYTES:
                raise ValueError("Manifest vượt giới hạn 5 MiB")
            members["workflow_manifest.json"] = manifest_path.read_bytes()
            manifest = read_json(members["workflow_manifest.json"])
            rows = manifest.get("files", [])
            if not isinstance(rows, list) or len(rows) > 1024:
                raise ValueError("manifest.files không hợp lệ")
            names: set[str] = {
                path
                for row in rows
                if isinstance(row, dict)
                for path in [row.get("path")]
                if isinstance(path, str)
            }
            names.update({"story.json", "story_validation.json", "series_anchor.json", "visual_bible.json", contract.video_prompt_file_name, "package_quality_report.json"})
            for group in ("characters", "landscape", "portrait"):
                folder = root / group
                if folder.is_dir():
                    names.update(p.relative_to(root).as_posix() for p in folder.iterdir() if p.is_file())
            total = len(members["workflow_manifest.json"])
            for name in sorted(names):
                path = root / name
                if not safe_name(name) or not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError(f"Member ngoài dự án: {name!r}")
                if path.is_file():
                    size = path.stat().st_size
                    total += size
                    if size > MAX_MEMBER_BYTES or total > MAX_PACKAGE_BYTES:
                        raise ValueError("Package vượt giới hạn dung lượng")
                    members[name] = path.read_bytes()
        result = inspect_members(members, contract=contract)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        result = inspect_members({})
        result["status"] = "FAIL"
        result["integrity_status"] = "FAIL"
        result["checks"].append({"check": "source", "status": "FAIL", "detector_class": "DETERMINISTIC", "detail": str(exc)})
    if overridden:
        result["status"] = "NOT_VERIFIED" if result["status"] != "FAIL" else "FAIL"
        result["integrity_status"] = "NOT_VERIFIED" if result["integrity_status"] != "FAIL" else "FAIL"
        result["publish_status"] = "NOT_VERIFIED" if result["publish_status"] != "FAIL" else "FAIL"
        result["checks"].append({"check": "preview_override", "status": "NOT_VERIFIED", "detector_class": "HOST_UNAVAILABLE",
                                 "detail": "Đang xem tệp thay thế: kết quả trên đĩa không xác minh bản xem thử."})
    return result
