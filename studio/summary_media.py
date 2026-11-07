"""Render planning and deterministic media inspection for Summary packages."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.summary_visual_schema import validate_summary_visual_plan

ORIENTATIONS = ("landscape", "portrait")
REVIEW_CHECKS = (
    "visual_fact",
    "source_grounding",
    "style_continuity",
    "entity_continuity",
    "numeric_fidelity",
    "text_quality",
    "safety",
)


def default_render_config() -> dict[str, Any]:
    return {
        "required_orientations": ["landscape"],
        "optional_orientations": ["portrait"],
        "generation_policy": "GENERATE_ALL",
        "max_attempts_per_asset": 3,
        "failure_policy": "PARTIAL",
        "include_sources_in_zip": False,
        "media_review_required": True,
    }


def validate_render_config(config: Any) -> list[str]:
    fields = {
        "required_orientations",
        "optional_orientations",
        "generation_policy",
        "max_attempts_per_asset",
        "failure_policy",
        "include_sources_in_zip",
        "media_review_required",
    }
    if not isinstance(config, Mapping) or set(config) != fields:
        return ["render_config không đúng closed schema"]
    errors: list[str] = []
    required = config.get("required_orientations")
    optional = config.get("optional_orientations")
    if (
        not isinstance(required, list)
        or not required
        or not set(required) <= set(ORIENTATIONS)
    ):
        errors.append("render_config.required_orientations không hợp lệ")
    if not isinstance(optional, list) or not set(optional) <= set(ORIENTATIONS):
        errors.append("render_config.optional_orientations không hợp lệ")
    if (
        isinstance(required, list)
        and isinstance(optional, list)
        and set(required) & set(optional)
    ):
        errors.append("orientation không được vừa required vừa optional")
    if config.get("generation_policy") != "GENERATE_ALL":
        errors.append("generation_policy phải là GENERATE_ALL")
    attempts = config.get("max_attempts_per_asset")
    if type(attempts) is not int or not 1 <= attempts <= 10:
        errors.append("max_attempts_per_asset phải từ 1 đến 10")
    if config.get("failure_policy") not in {"PARTIAL", "BLOCK"}:
        errors.append("failure_policy không hợp lệ")
    for field in ("include_sources_in_zip", "media_review_required"):
        if type(config.get(field)) is not bool:
            errors.append(f"render_config.{field} phải là boolean")
    return errors


def build_render_plan(
    summary: Mapping[str, Any],
    visual_plan: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    selected = dict(config or default_render_config())
    errors = validate_render_config(selected) + validate_summary_visual_plan(
        visual_plan, summary
    )
    if errors:
        raise ValueError("Không thể tạo render plan: " + "; ".join(errors))
    visual_raw = _canonical_bytes(visual_plan)
    assets = []
    orientations = list(selected["required_orientations"]) + list(
        selected["optional_orientations"]
    )
    for scene in visual_plan["scenes"]:
        for orientation in orientations:
            asset_id = f"{scene['scene_id']}_{orientation}"
            assets.append(
                {
                    "asset_id": asset_id,
                    "scene_id": scene["scene_id"],
                    "orientation": orientation,
                    "required": orientation in selected["required_orientations"],
                    "output_path": f"{orientation}/{scene['scene_id']}.png",
                    "prompt_sha256": hashlib.sha256(
                        str(scene[f"{orientation}_prompt"]).encode("utf-8")
                    ).hexdigest(),
                    "status": "PENDING",
                    "attempt_count": 0,
                }
            )
    return {
        "schema_version": "1.0.0",
        "prompt_version": "1.5.0",
        "source_visual_plan_sha256": hashlib.sha256(visual_raw).hexdigest(),
        "config": selected,
        "assets": assets,
    }


def validate_render_plan(plan: Any) -> list[str]:
    root = {
        "schema_version",
        "prompt_version",
        "source_visual_plan_sha256",
        "config",
        "assets",
    }
    asset_fields = {
        "asset_id",
        "scene_id",
        "orientation",
        "required",
        "output_path",
        "prompt_sha256",
        "status",
        "attempt_count",
    }
    if not isinstance(plan, Mapping) or set(plan) != root:
        return ["summary_render_plan.json không đúng closed schema"]
    errors = validate_render_config(plan.get("config"))
    if plan.get("schema_version") != "1.0.0" or plan.get("prompt_version") != "1.5.0":
        errors.append("summary_render_plan version không hợp lệ")
    if not _sha(plan.get("source_visual_plan_sha256")):
        errors.append("source_visual_plan_sha256 không hợp lệ")
    rows = plan.get("assets")
    if not isinstance(rows, list) or not rows:
        errors.append("summary_render_plan.assets phải là array không rỗng")
        return errors
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, Mapping) or set(row) != asset_fields:
            errors.append(f"render assets[{index}] không đúng closed schema")
            continue
        path = row.get("output_path")
        if not _safe_media_path(path, row.get("orientation")):
            errors.append(f"render assets[{index}].output_path không hợp lệ")
        asset_id = row.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip() or asset_id in seen:
            errors.append(f"render assets[{index}].asset_id không hợp lệ hoặc trùng")
        else:
            seen.add(asset_id)
        if (
            row.get("orientation") not in ORIENTATIONS
            or type(row.get("required")) is not bool
        ):
            errors.append(f"render assets[{index}] orientation/required không hợp lệ")
        if not _text(row.get("scene_id")) or not _sha(row.get("prompt_sha256")):
            errors.append(f"render assets[{index}] scene/prompt hash không hợp lệ")
        if row.get("status") not in {
            "PENDING",
            "GENERATING",
            "GENERATED",
            "VALIDATED",
            "FAILED",
            "RETRY_PENDING",
        }:
            errors.append(f"render assets[{index}].status không hợp lệ")
        if type(row.get("attempt_count")) is not int or row["attempt_count"] < 0:
            errors.append(f"render assets[{index}].attempt_count không hợp lệ")
    return errors


def inspect_rendered_media(
    render_plan: Mapping[str, Any],
    media: Mapping[str, bytes],
    approved_review: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    errors = validate_render_plan(render_plan)
    if errors:
        raise ValueError("Render plan không hợp lệ: " + "; ".join(errors))
    approvals = _review_approvals(approved_review)
    known_asset_ids = {row["asset_id"] for row in render_plan["assets"]}
    unknown_approvals = set(approvals) - known_asset_ids
    if unknown_approvals:
        raise ValueError(
            "Media review tham chiếu asset không tồn tại: "
            + ", ".join(sorted(unknown_approvals))
        )
    log_assets = []
    review_assets = []
    hashes: dict[str, str] = {}
    required_total = required_valid = failed = 0
    expected_paths = {row["output_path"] for row in render_plan["assets"]}
    extra_paths = sorted(set(media) - expected_paths)
    for row in render_plan["assets"]:
        path = row["output_path"]
        raw = media.get(path)
        issues: list[str] = []
        optional_absent = raw is None and not row["required"]
        width = height = None
        digest = None
        if row["required"]:
            required_total += 1
        if raw is None:
            if row["required"]:
                issues.append("MISSING_ASSET")
        elif not raw:
            issues.append("EMPTY_FILE")
        else:
            digest = hashlib.sha256(raw).hexdigest()
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    image.verify()
                with Image.open(io.BytesIO(raw)) as image:
                    width, height = image.size
            except (OSError, UnidentifiedImageError):
                issues.append("CORRUPT_IMAGE")
            if width is not None and height is not None:
                if row["orientation"] == "landscape" and width <= height:
                    issues.append("WRONG_ORIENTATION")
                if row["orientation"] == "portrait" and height <= width:
                    issues.append("WRONG_ORIENTATION")
            if digest in hashes:
                issues.append("DUPLICATE_IMAGE")
            elif digest:
                hashes[digest] = path
        technical = (
            "NOT_APPLICABLE" if optional_absent else "PASS" if not issues else "FAIL"
        )
        approved = approvals.get(row["asset_id"])
        semantic_checks = (
            dict(approved["checks"])
            if approved is not None
            else {
                name: "NOT_CHECKED" if raw and not issues else "NOT_APPLICABLE"
                for name in REVIEW_CHECKS
            }
        )
        review_pass = all(
            value in {"PASS", "NOT_APPLICABLE"} for value in semantic_checks.values()
        )
        status = (
            "PASS"
            if technical == "PASS"
            and (review_pass or not render_plan["config"]["media_review_required"])
            else "PENDING_REVIEW"
        )
        if optional_absent:
            status = "NOT_APPLICABLE"
        if issues:
            status = "FAIL"
            failed += 1
        if row["required"] and status == "PASS":
            required_valid += 1
        log_assets.append(
            {
                "asset_id": row["asset_id"],
                "path": path,
                "status": (
                    "NOT_APPLICABLE"
                    if optional_absent
                    else "GENERATED"
                    if raw is not None and not issues
                    else "FAILED"
                ),
                "size_bytes": len(raw) if raw is not None else None,
                "sha256": digest,
                "width": width,
                "height": height,
                "issues": issues,
            }
        )
        review_assets.append(
            {
                "asset_id": row["asset_id"],
                "scene_id": row["scene_id"],
                "path": path,
                "technical_status": technical,
                "checks": semantic_checks,
                "status": status,
                "issues": issues,
                "recommended_action": (
                    None
                    if optional_absent
                    else "RENDER_AGAIN"
                    if issues
                    else "HUMAN_REVIEW"
                ),
            }
        )
    package_status = (
        "COMPLETE"
        if required_valid == required_total and not extra_paths and failed == 0
        else "PARTIAL"
    )
    if render_plan["config"]["failure_policy"] == "BLOCK" and (
        failed or required_valid < required_total
    ):
        package_status = "BLOCKED"
    return (
        {
            "schema_version": "1.0.0",
            "prompt_version": "1.5.0",
            "assets": log_assets,
            "extra_paths": extra_paths,
        },
        {
            "schema_version": "1.0.0",
            "prompt_version": "1.5.0",
            "visual_plan_sha256": render_plan["source_visual_plan_sha256"],
            "assets": review_assets,
            "metrics": {
                "required_assets": required_total,
                "validated_assets": required_valid,
                "failed_assets": failed,
                "coverage_percent": round(required_valid * 100 / required_total, 2)
                if required_total
                else 100,
            },
        },
        package_status,
    )


def finalize_render_plan(
    render_plan: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a package snapshot whose asset states reflect the media review."""
    import copy

    finalized = copy.deepcopy(dict(render_plan))
    reviews = {
        row["asset_id"]: row
        for row in review.get("assets", [])
        if isinstance(row, Mapping) and isinstance(row.get("asset_id"), str)
    }
    for asset in finalized["assets"]:
        status = reviews.get(asset["asset_id"], {}).get("status")
        asset["status"] = {
            "PASS": "VALIDATED",
            "PENDING_REVIEW": "GENERATED",
            "FAIL": "FAILED",
            "NOT_APPLICABLE": "PENDING",
        }.get(status, "FAILED") if isinstance(status, str) else "FAILED"
        issues = reviews.get(asset["asset_id"], {}).get("issues", [])
        if status not in {None, "NOT_APPLICABLE"} and "MISSING_ASSET" not in issues:
            asset["attempt_count"] = max(1, asset["attempt_count"])
    return finalized


def load_media_root(root: Path) -> dict[str, bytes]:
    media: dict[str, bytes] = {}
    for orientation in ORIENTATIONS:
        directory = root / orientation
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Không chấp nhận symlink media: {path}")
            if path.is_file():
                media[path.relative_to(root).as_posix()] = path.read_bytes()
    return media


def _review_approvals(review: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if review is None:
        return {}
    if (
        not isinstance(review, Mapping)
        or set(review) != {"schema_version", "assets"}
        or review.get("schema_version") != "1.0.0"
    ):
        raise ValueError("Media review đầu vào không đúng closed schema")
    rows = review.get("assets")
    if not isinstance(rows, list):
        raise ValueError("Media review assets phải là array")
    approvals: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, Mapping) or set(row) != {"asset_id", "checks"}:
            raise ValueError(f"Media review assets[{index}] không đúng closed schema")
        checks = row.get("checks")
        if not isinstance(checks, Mapping) or set(checks) != set(REVIEW_CHECKS):
            raise ValueError(f"Media review assets[{index}].checks không hợp lệ")
        if any(
            value not in {"PASS", "FAIL", "NOT_APPLICABLE"} for value in checks.values()
        ):
            raise ValueError(f"Media review assets[{index}] có trạng thái không hợp lệ")
        asset_id = row.get("asset_id")
        if not _text(asset_id) or asset_id in approvals:
            raise ValueError(
                f"Media review assets[{index}].asset_id không hợp lệ hoặc trùng"
            )
        approvals[str(asset_id)] = row
    return approvals


def _canonical_bytes(value: object) -> bytes:
    import json

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_media_path(value: object, orientation: object) -> bool:
    if not isinstance(value, str) or orientation not in ORIENTATIONS or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and len(path.parts) == 2
        and path.parts[0] == orientation
    )


__all__ = [
    "REVIEW_CHECKS",
    "build_render_plan",
    "default_render_config",
    "finalize_render_plan",
    "inspect_rendered_media",
    "load_media_root",
    "validate_render_config",
    "validate_render_plan",
]
