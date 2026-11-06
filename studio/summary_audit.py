"""Deterministic auditing for canonical Summary directories and ZIP packages."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.artifact_validation import strict_json_bytes
from studio.image_prompt_validation import validate_image_prompt_plan
from studio.story_schema import validate_story_document
from studio.summary_media import REVIEW_CHECKS, validate_render_plan
from studio.summary_schema import validate_summary_document
from studio.summary_visual_schema import validate_summary_visual_plan
from studio.video_prompt_v4 import validate_v5_plan
from studio.workflow_package import read_archive, validate_visual_plan

MANIFEST_FIELDS = {
    "schema_version",
    "prompt_version",
    "status",
    "parent_package_sha256",
    "source_fingerprints",
    "files",
}
FILE_FIELDS = {"path", "size_bytes", "sha256", "origin"}
MEDIA_FILE_FIELDS = FILE_FIELDS | {
    "asset_id",
    "scene_id",
    "orientation",
    "media_type",
    "width",
    "height",
    "review_status",
}


@dataclass
class SummaryAuditResult:
    status: str = "PASS"
    checks: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.status = "FAIL"
        self.errors.append(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact": "summary_package",
            "status": self.status,
            "checks": self.checks,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _directory_members(root: Path) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Không chấp nhận symlink: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            members[relative] = path.read_bytes()
    return members


def load_summary_members(path: Path) -> dict[str, bytes]:
    if path.is_dir():
        return _directory_members(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        return read_archive(path)
    raise ValueError("Summary audit yêu cầu thư mục hoặc tệp ZIP")


def is_summary_package(path: Path) -> bool:
    if path.is_dir():
        return (path / "summary.json").is_file()
    if path.is_file() and path.suffix.lower() == ".zip":
        try:
            return "summary.json" in read_archive(path)
        except (OSError, ValueError):
            return path.name.startswith("summary_")
    return False


def _json(
    members: Mapping[str, bytes], name: str, result: SummaryAuditResult
) -> Mapping[str, Any] | None:
    raw = members.get(name)
    if raw is None:
        result.fail(f"Thiếu {name}")
        return None
    try:
        return strict_json_bytes(raw)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result.fail(f"{name} không hợp lệ: {exc}")
        return None


def _audit_manifest(members: Mapping[str, bytes], result: SummaryAuditResult) -> None:
    manifest = _json(members, "summary_manifest.json", result)
    if manifest is None:
        result.checks["manifest"] = "FAIL"
        return
    if (
        set(manifest) != MANIFEST_FIELDS
        or manifest.get("schema_version") != "1.1.0"
        or manifest.get("prompt_version") != "1.4.0"
    ):
        result.fail("summary_manifest.json không đúng closed schema/version")
    if manifest.get("status") not in {"COMPLETE", "PARTIAL", "BLOCKED"}:
        result.fail("summary_manifest.status không hợp lệ")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        result.fail("summary_manifest.files phải là array")
        rows = []
    declared: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, Mapping) or frozenset(row) not in {
            frozenset(FILE_FIELDS),
            frozenset(MEDIA_FILE_FIELDS),
        }:
            result.fail(f"summary_manifest.files[{index}] không đúng closed schema")
            continue
        name = row.get("path")
        if (
            not isinstance(name, str)
            or name in declared
            or name == "summary_manifest.json"
        ):
            result.fail(f"summary_manifest.files[{index}].path không hợp lệ hoặc trùng")
            continue
        declared.add(name)
        raw = members.get(name)
        if raw is None:
            result.fail(f"Manifest tham chiếu tệp không tồn tại: {name}")
            continue
        if (
            row.get("size_bytes") != len(raw)
            or row.get("sha256") != hashlib.sha256(raw).hexdigest()
        ):
            result.fail(f"Manifest size/hash không khớp: {name}")
        if not isinstance(row.get("origin"), str) or not row["origin"].strip():
            result.fail(f"Manifest origin không hợp lệ: {name}")
        if (
            isinstance(name, str)
            and name.startswith(("landscape/", "portrait/"))
            and set(row) != MEDIA_FILE_FIELDS
        ):
            result.fail(f"Media thiếu metadata manifest: {name}")
        if set(row) == MEDIA_FILE_FIELDS:
            _audit_media_manifest_row(row, raw, result)
    actual = set(members) - {"summary_manifest.json"}
    if declared != actual:
        result.fail("Manifest file set không khớp payload")
    result.checks["manifest"] = "PASS" if not result.errors else "FAIL"


def _audit_media_manifest_row(
    row: Mapping[str, Any],
    raw: bytes,
    result: SummaryAuditResult,
) -> None:
    name = str(row["path"])
    orientation = row.get("orientation")
    if orientation not in {"landscape", "portrait"} or not name.startswith(
        f"{orientation}/"
    ):
        result.fail(f"Media orientation/path không khớp: {name}")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            media_type = Image.MIME.get(image.format, "application/octet-stream")
    except (OSError, UnidentifiedImageError):
        result.fail(f"Media không giải mã được: {name}")
        return
    if (
        row.get("width") != width
        or row.get("height") != height
        or row.get("media_type") != media_type
    ):
        result.fail(f"Media metadata không khớp: {name}")
    if orientation == "landscape" and width <= height:
        result.fail(f"Media không đúng landscape: {name}")
    if orientation == "portrait" and height <= width:
        result.fail(f"Media không đúng portrait: {name}")
    if row.get("review_status") not in {"PASS", "FAIL", "PENDING_REVIEW"}:
        result.fail(f"Media review_status không hợp lệ: {name}")


def _audit_media_contracts(
    members: Mapping[str, bytes],
    result: SummaryAuditResult,
) -> None:
    names = (
        "summary_render_plan.json",
        "summary_render_log.json",
        "summary_media_review.json",
    )
    present = [name in members for name in names]
    if any(present) and not all(present):
        result.fail("Media workflow phải có đủ render plan, render log và media review")
        return
    if not all(present):
        return
    plan = _json(members, names[0], result)
    review = _json(members, names[2], result)
    if plan is None or review is None:
        return
    for error in validate_render_plan(plan):
        result.fail(error)
    review_rows = review.get("assets") if isinstance(review, Mapping) else None
    if not isinstance(review_rows, list):
        result.fail("summary_media_review.assets phải là array")
        return
    by_id = {
        row.get("asset_id"): row for row in review_rows if isinstance(row, Mapping)
    }
    media_hashes: dict[str, str] = {}
    for name, raw in members.items():
        if not name.startswith(("landscape/", "portrait/")):
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if digest in media_hashes:
            result.fail(f"Media trùng hash: {media_hashes[digest]} và {name}")
        else:
            media_hashes[digest] = name
    for asset in plan.get("assets", []):
        row = by_id.get(asset.get("asset_id"))
        if not isinstance(row, Mapping):
            result.fail(f"Thiếu media review: {asset.get('asset_id')}")
            continue
        checks = row.get("checks")
        if not isinstance(checks, Mapping) or set(checks) != set(REVIEW_CHECKS):
            result.fail(f"Media review checks không hợp lệ: {asset.get('asset_id')}")
        if (
            asset.get("required")
            and row.get("status") == "PASS"
            and asset.get("output_path") not in members
        ):
            result.fail(
                f"Media review PASS nhưng thiếu file: {asset.get('output_path')}"
            )
        if (
            asset.get("required")
            and row.get("status") == "PASS"
            and asset.get("status") != "VALIDATED"
        ):
            result.fail(
                "Media review PASS nhưng render plan chưa VALIDATED: "
                f"{asset.get('asset_id')}"
            )
    manifest = _json(members, "summary_manifest.json", result)
    if manifest is not None and manifest.get("status") == "COMPLETE":
        incomplete = [
            asset["asset_id"]
            for asset in plan.get("assets", [])
            if asset.get("required")
            and by_id.get(asset["asset_id"], {}).get("status") != "PASS"
        ]
        if incomplete:
            result.fail("Package COMPLETE nhưng còn media bắt buộc chưa PASS")
    result.checks["rendered_media"] = "PASS" if not result.errors else "FAIL"


def audit_summary_package(path: Path) -> SummaryAuditResult:
    result = SummaryAuditResult()
    try:
        members = load_summary_members(path)
    except (OSError, ValueError) as exc:
        result.fail(f"Không đọc được package: {exc}")
        return result
    summary = _json(members, "summary.json", result)
    if summary is not None:
        for error in validate_summary_document(summary):
            result.fail(error)
    result.checks["summary_schema"] = (
        "PASS" if summary is not None and not result.errors else "FAIL"
    )
    _audit_manifest(members, result)
    _audit_media_contracts(members, result)

    summary_visual = (
        _json(members, "summary_visual_plan.json", result)
        if "summary_visual_plan.json" in members
        else None
    )
    if summary_visual is not None and summary is not None:
        errors = validate_summary_visual_plan(summary_visual, summary)
        for error in errors:
            result.fail(error)
        result.checks["summary_visual_plan"] = "PASS" if not errors else "FAIL"

    story = _json(members, "story.json", result) if "story.json" in members else None
    if story is not None:
        for error in validate_story_document(story):
            result.fail(error)
        result.checks["story_projection"] = (
            "PASS" if not validate_story_document(story) else "FAIL"
        )
    visual = (
        _json(members, "visual_plan.json", result)
        if "visual_plan.json" in members
        else None
    )
    if visual is not None:
        for error in validate_visual_plan(visual):
            result.fail(error)
        result.checks["visual_projection"] = (
            "PASS" if not validate_visual_plan(visual) else "FAIL"
        )
    image_plan = (
        _json(members, "image_prompts.json", result)
        if "image_prompts.json" in members
        else None
    )
    if image_plan is not None and story is not None:
        story_raw = members["story.json"]
        errors = validate_image_prompt_plan(
            image_plan, story, story_raw, expected_prompt_version="5.2.2"
        )
        for error in errors:
            result.fail(error)
        result.checks["image_projection"] = "PASS" if not errors else "FAIL"
    video_plan = (
        _json(members, "video_prompts.json", result)
        if "video_prompts.json" in members
        else None
    )
    if video_plan is not None and story is not None:
        projection = validate_v5_plan(video_plan, members=members)
        for error in projection["errors"]:
            result.fail(error)
        result.checks["video_projection"] = (
            "PASS" if not projection["errors"] else "FAIL"
        )
    return result


__all__ = [
    "SummaryAuditResult",
    "audit_summary_package",
    "is_summary_package",
    "load_summary_members",
]
