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
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.artifact_validation import strict_json_bytes
from studio.prompt_contract import PromptContract, load_prompt_contract

WORKFLOW_FILES = {"workflow": "manifest.json", "visual_bible": "visual_plan.json", "video_prompts": "video_prompts.json"}
STAGES = ("STAGE1", "STAGE2", "STAGE3", "STAGE4")
PURPOSES: tuple[str, ...] = ()
MANIFEST_FIELDS = ("schema_version", "prompt_version", "stage", "status", "parent_package_sha256", "files")
FILE_FIELDS = ("path", "size_bytes", "sha256", "origin_stage")
VALIDATION_FIELDS: tuple[str, ...] = ()
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 5 * 1024 * 1024
ZONE_BASENAMES = ("cover.png", "greeting.png", "opening.png", "introduction.png", "development.png", "climax.png", "falling.png", "ending.png", "farewell.png", "outro.png")


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


def _stage_label(stage: Any) -> str | None:
    return f"STAGE{stage}" if type(stage) is int and 1 <= stage <= 4 else None


def _expected_payload(members: Mapping[str, bytes], stage: int) -> set[str]:
    expected = {"story.json", "validation_report.json"}
    story = read_json(members.get("story.json", b"{}"))
    if isinstance(story.get("meta"), Mapping) and story["meta"].get("profile") == "SERIAL_DETECTIVE":
        expected.add("series_anchor.json")
    story_only = False
    if stage == 4 and "video_prompts.json" in members:
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
    if stage == 4:
        expected.add("video_prompts.json")
    return expected


def package_digest(rows: list[Mapping[str, Any]]) -> str:
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def inspect_members(members: Mapping[str, bytes], *, archive: bool = False, parent: Mapping[str, bytes] | None = None,
                    contract: PromptContract | None = None, overridden: bool = False) -> dict[str, Any]:
    contract = contract or load_prompt_contract()
    checks: list[dict[str, str]] = []
    def check(name: str, ok: bool, good: str, bad: str) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detector_class": "DETERMINISTIC", "detail": good if ok else bad})
    if "manifest.json" not in members:
        check("manifest_schema", False, "", "Thiếu manifest.json v4.1.6")
        return {"status": "FAIL", "integrity_status": "FAIL", "publish_status": "FAIL", "compatibility": "UNSUPPORTED", "stage": None, "checks": checks, "files": [], "manifest": {}, "actual_package_digest_sha256": None}
    try:
        manifest = read_json(members["manifest.json"])
    except ValueError as exc:
        check("manifest_schema", False, "", f"manifest.json không hợp lệ: {exc}")
        return {"status": "FAIL", "integrity_status": "FAIL", "publish_status": "FAIL", "compatibility": "UNSUPPORTED", "stage": None, "checks": checks, "files": [], "manifest": {}, "actual_package_digest_sha256": None}
    stage, rows = manifest.get("stage"), manifest.get("files")
    stage_label = _stage_label(stage)
    digest_pattern = re.compile(r"[0-9a-f]{64}")
    parent_digest = manifest.get("parent_package_sha256")
    schema_ok = (set(manifest) == set(MANIFEST_FIELDS) and manifest.get("schema_version") == "4.1.3"
                 and manifest.get("prompt_version") == contract.version_label and stage_label is not None
                 and manifest.get("status") in {"COMPLETE", "PARTIAL", "BLOCKED"}
                 and (parent_digest is None or isinstance(parent_digest, str) and digest_pattern.fullmatch(parent_digest)))
    check("manifest_schema", schema_ok, "Manifest v4.1.6 / schema 4.1.3 hợp lệ.", "Manifest không đúng schema v4.1.6 (không hỗ trợ gói cũ).")
    row_ok, indexed = isinstance(rows, list), {}
    if row_ok:
        paths = []
        for row in rows:
            valid = (isinstance(row, Mapping) and set(row) == set(FILE_FIELDS) and isinstance(row.get("path"), str)
                     and safe_name(row["path"]) and type(row.get("size_bytes")) is int and row["size_bytes"] >= 0
                     and (row.get("sha256") is None or (isinstance(row.get("sha256"), str)
                          and digest_pattern.fullmatch(row["sha256"])))
                     and type(row.get("origin_stage")) is int and 1 <= row["origin_stage"] <= 4)
            if not valid:
                row_ok = False
                break
            paths.append(row["path"])
            indexed[row["path"]] = row
        row_ok = row_ok and paths == sorted(paths) and len(paths) == len(set(p.casefold() for p in paths))
    check("manifest_files", row_ok, "Danh sách manifest hợp lệ.", "manifest.files không hợp lệ.")
    actual_payload, listed = set(members) - {"manifest.json"}, set(indexed)
    file_set_ok = row_ok and actual_payload == listed
    if stage_label:
        try:
            expected_payload = _expected_payload(members, stage)
            required_payload = {"story.json", "validation_report.json"}
            if stage == 4:
                required_payload.add("video_prompts.json")
            if manifest.get("status") == "COMPLETE":
                file_set_ok = file_set_ok and actual_payload == expected_payload
            else:
                file_set_ok = file_set_ok and required_payload <= actual_payload <= expected_payload
        except (ValueError, KeyError):
            file_set_ok = False
    check("file_set", file_set_ok, f"Exact file set Stage {stage} hợp lệ.", "File set không đúng stage/schema v4.1.6.")
    digest_ok = row_ok
    for path, row in indexed.items():
        raw = members.get(path)
        digest_ok = bool(digest_ok and raw is not None and len(raw) == row["size_bytes"])
        if raw is not None and row.get("sha256") is not None:
            digest_ok = digest_ok and hashlib.sha256(raw).hexdigest() == row["sha256"]
    check("file_digest", digest_ok, "Size/hash mọi payload khớp manifest.", "Size/hash payload không khớp manifest.")
    json_ok = True
    for path, raw in members.items():
        if path.endswith(".json"):
            try:
                json_ok = json_ok and read_json(raw).get("schema_version") == "4.1.3"
            except ValueError:
                json_ok = False
    check("strict_json", json_ok, "Mọi JSON parse strict và dùng schema 4.1.3.", "JSON lỗi hoặc schema_version không phải 4.1.3.")
    report_ok = False
    try:
        report = read_json(members["validation_report.json"])
        report_ok = (
            set(report) == {"schema_version", "prompt_version", "stage", "status", "input_sources",
                            "checks", "limitations", "remaining_work", "archive_validation"}
            and report.get("schema_version") == "4.1.3"
            and report.get("prompt_version") == "4.1.6"
            and report.get("stage") == stage
            and report.get("status") == manifest.get("status")
            and isinstance(report.get("checks"), list)
        )
    except (KeyError, ValueError):
        report_ok = False
    check("validation_report", report_ok, "Report khớp schema, prompt, stage và trạng thái manifest.",
          "validation_report.json không khớp manifest hoặc closed schema v4.1.6.")

    image_ok = True
    if stage_label and stage >= 2 and "visual_plan.json" in members:
        try:
            plan = read_json(members["visual_plan.json"])
            targets = plan["targets"]
            aspects = ("landscape",) if stage == 2 else ("landscape", "portrait")
            image_names = active_image_basenames(plan)
            reference_names = [
                row.get("reference_path") for row in plan.get("characters", [])
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
                        target = targets.get(aspect, {})
                        if target.get("size_policy") == "EXACT":
                            image_ok = image_ok and (width, height) == (target.get("width"), target.get("height"))
        except (KeyError, TypeError, ValueError, UnidentifiedImageError, OSError):
            image_ok = False
    check("image_files", image_ok, "PNG giải mã được và đạt orientation/size policy.",
          "Ảnh không phải PNG hợp lệ hoặc sai orientation/size policy.")
    success = all(row["status"] == "PASS" for row in checks)
    payload_rows = [dict(indexed[path]) for path in sorted(indexed)] if row_ok else []
    return {"status": "PASS" if success else "FAIL", "integrity_status": "PASS" if success else "FAIL",
            "publish_status": "PASS" if success and manifest.get("status") == "COMPLETE" else "FAIL",
            "compatibility": "NATIVE_CURRENT" if schema_ok else "UNSUPPORTED", "stage": stage_label,
            "package_stage": stage_label, "checks": checks, "manifest": manifest, "files": payload_rows,
            "actual_package_digest_sha256": package_digest(payload_rows) if row_ok else None,
            "overridden": overridden, "archive": archive}


def inspect_directory(root: Path, *, overridden: bool = False, parent: Mapping[str, bytes] | None = None,
                      contract: PromptContract | None = None) -> dict[str, Any]:
    try:
        manifest = read_json((root / "manifest.json").read_bytes())
        names = {"manifest.json", *(row["path"] for row in manifest.get("files", []) if isinstance(row, Mapping) and isinstance(row.get("path"), str))}
        members = {name: (root / Path(name)).read_bytes() for name in names}
        return inspect_members(members, parent=parent, contract=contract, overridden=overridden)
    except (OSError, ValueError, KeyError) as exc:
        result = inspect_members({}, contract=contract)
        result["checks"].append({"check": "directory", "status": "FAIL", "detector_class": "DETERMINISTIC", "detail": str(exc)})
        return result


__all__ = ["FILE_FIELDS", "MANIFEST_FIELDS", "PURPOSES", "STAGES", "VALIDATION_FIELDS", "WORKFLOW_FILES", "active_image_basenames", "inspect_directory", "inspect_members", "package_digest", "read_archive", "read_json", "safe_name"]
