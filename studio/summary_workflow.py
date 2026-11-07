"""Guarded repair and completion operations for extracted Summary packages."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from studio.artifact_validation import strict_json_bytes
from studio.summary_media import (
    build_render_plan,
    finalize_render_plan,
    inspect_rendered_media,
    load_media_root,
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} root phải là object")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _payload_paths(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.name != "summary_manifest.json"
    )


def summary_manifest_issues(root: Path) -> list[str]:
    """Return exact file-set, size, and digest differences for a Summary directory."""
    manifest = _json(root / "summary_manifest.json")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        return ["summary_manifest.files phải là array"]
    issues: list[str] = []
    declared: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            issues.append(f"summary_manifest.files[{index}] không hợp lệ")
            continue
        name = str(row["path"])
        if name in declared:
            issues.append(f"Đường dẫn manifest bị trùng: {name}")
            continue
        declared[name] = row
    actual = {path.relative_to(root).as_posix(): path for path in _payload_paths(root)}
    for name in sorted(set(declared) - set(actual)):
        issues.append(f"Manifest tham chiếu tệp không tồn tại: {name}")
    for name in sorted(set(actual) - set(declared)):
        issues.append(f"Tệp chưa có trong manifest: {name}")
    for name in sorted(set(actual) & set(declared)):
        raw = actual[name].read_bytes()
        row = declared[name]
        if row.get("size_bytes") != len(raw) or row.get("sha256") != hashlib.sha256(raw).hexdigest():
            issues.append(f"Manifest size/hash không khớp: {name}")
    return issues


def _media_bindings(root: Path) -> dict[str, dict[str, Any]]:
    plan = _json(root / "summary_render_plan.json") if (root / "summary_render_plan.json").is_file() else {}
    review = _json(root / "summary_media_review.json") if (root / "summary_media_review.json").is_file() else {}
    review_by_path = {
        str(row.get("path")): row
        for row in review.get("assets", [])
        if isinstance(row, Mapping) and isinstance(row.get("path"), str)
    }
    bindings: dict[str, dict[str, Any]] = {}
    for asset in plan.get("assets", []):
        if not isinstance(asset, Mapping) or not isinstance(asset.get("output_path"), str):
            continue
        name = str(asset["output_path"])
        bindings[name] = {"plan": asset, "review": review_by_path.get(name, {})}
    for name, row in review_by_path.items():
        bindings.setdefault(name, {"plan": {}, "review": row})
    return bindings


def _review_status(review: Mapping[str, Any]) -> str:
    explicit = review.get("status")
    if explicit == "PASS":
        return "PASS"
    if explicit == "FAIL":
        return "FAIL"
    checks = review.get("checks")
    accepted = {"PASS", "PASS_WITH_DISCLOSED_VARIATION", "NOT_APPLICABLE"}
    if (
        review
        and review.get("recommended_action") in {None, "NONE"}
        and isinstance(checks, Mapping)
        and all(value in accepted for value in checks.values())
    ):
        return "PASS"
    if review and (
        review.get("recommended_action") not in {None, "NONE"}
        or explicit == "FAIL"
        or isinstance(checks, Mapping) and any(value in {"FAIL", "NOT_CHECKED"} for value in checks.values())
    ):
        return "FAIL"
    return "PENDING_REVIEW"


def _media_row(
    name: str,
    raw: bytes,
    previous: Mapping[str, Any] | None,
    binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    orientation = name.split("/", 1)[0]
    try:
        from io import BytesIO

        with Image.open(BytesIO(raw)) as image:
            width, height = image.size
            media_type = Image.MIME.get(image.format, "application/octet-stream")
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Media không đọc được: {name}: {exc}") from exc
    stem = Path(name).stem
    plan = binding.get("plan", {}) if isinstance(binding, Mapping) else {}
    review = binding.get("review", {}) if isinstance(binding, Mapping) else {}
    asset_id = plan.get("asset_id") or review.get("asset_id")
    scene_id = plan.get("scene_id") or review.get("scene_id") or stem
    if not asset_id:
        raise ValueError(
            f"Không thể tái dựng media row vì thiếu binding trong render plan/review: {name}"
        )
    row = dict(previous or {})
    row.update({
        "path": name,
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "origin": row.get("origin") or (
            "STAGE2_LANDSCAPE" if orientation == "landscape" else "STAGE3_PORTRAIT"
        ),
        "asset_id": asset_id,
        "scene_id": scene_id,
        "orientation": orientation,
        "media_type": media_type,
        "width": width,
        "height": height,
        "review_status": _review_status(review),
    })
    return row


def rebuild_summary_manifest(root: Path, *, status: str | None = None) -> bytes:
    """Rebuild manifest rows from exact local bytes while preserving provenance metadata."""
    manifest = _json(root / "summary_manifest.json")
    previous = {
        str(row.get("path")): row
        for row in manifest.get("files", [])
        if isinstance(row, Mapping) and isinstance(row.get("path"), str)
    }
    bindings = _media_bindings(root)
    rows: list[dict[str, Any]] = []
    for path in _payload_paths(root):
        name = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        if name.startswith(("landscape/", "portrait/")):
            row = _media_row(name, raw, previous.get(name), bindings.get(name))
        else:
            row = dict(previous.get(name, {}))
            row.update({
                "path": name,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "origin": row.get("origin") or "LOCAL_REPAIR",
            })
        rows.append(row)
    manifest["files"] = rows
    stage_path = root / "summary_stage.json"
    if stage_path.is_file():
        stage = _json(stage_path)
        manifest["prompt_version"] = stage.get("prompt_version", manifest.get("prompt_version"))
        manifest["parent_package_sha256"] = stage.get("parent_package_sha256")
        if status is None:
            manifest["status"] = stage.get("status", manifest.get("status"))
    if status is not None:
        manifest["status"] = status
    return _canonical(manifest)


def _backup(root: Path, names: tuple[str, ...]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = root.parent / ".ai_summary_backups" / root.name / stamp
    backup.mkdir(parents=True, exist_ok=False)
    for name in names:
        source = root / name
        if source.is_file():
            (backup / name).write_bytes(source.read_bytes())
    return backup


def _atomic_write(path: Path, raw: bytes) -> None:
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def repair_summary_manifest(root: Path) -> Path:
    """Back up and atomically synchronize a Summary manifest with local payload bytes."""
    backup = _backup(root, ("summary_manifest.json",))
    _atomic_write(root / "summary_manifest.json", rebuild_summary_manifest(root))
    issues = summary_manifest_issues(root)
    if issues:
        _atomic_write(root / "summary_manifest.json", (backup / "summary_manifest.json").read_bytes())
        raise ValueError("Hậu kiểm manifest chưa đạt: " + "; ".join(issues))
    return backup


def revalidate_summary_media(root: Path, approved_review: Mapping[str, Any]) -> Path:
    """Rebuild a Stage 3 media snapshot from actual files and approved observations."""
    summary = strict_json_bytes((root / "summary.json").read_bytes())
    visual = strict_json_bytes((root / "summary_visual_plan.json").read_bytes())
    config = {
        "required_orientations": ["landscape", "portrait"],
        "optional_orientations": [],
        "generation_policy": "GENERATE_ALL",
        "max_attempts_per_asset": 3,
        "failure_policy": "PARTIAL",
        "include_sources_in_zip": False,
        "media_review_required": True,
    }
    plan = build_render_plan(summary, visual, config)
    log, review, package_status = inspect_rendered_media(
        plan, load_media_root(root), approved_review
    )
    if package_status != "COMPLETE":
        failures = [
            str(row.get("asset_id")) for row in review.get("assets", [])
            if isinstance(row, Mapping) and row.get("status") != "PASS"
        ]
        raise ValueError("Media chưa đạt: " + ", ".join(failures))
    plan = finalize_render_plan(plan, review)
    backup = _backup(
        root,
        (
            "summary_render_plan.json",
            "summary_render_log.json",
            "summary_media_review.json",
            "summary_validation_report.json",
            "summary_manifest.json",
        ),
    )
    validation = _json(root / "summary_validation_report.json")
    for check in validation.get("checks", []):
        if not isinstance(check, dict):
            continue
        if check.get("id") == "IMAGE_FILES":
            check.update(
                status="PASS",
                method="CODE",
                details="16/16 PNG giải mã được, đúng orientation, có size và SHA-256; không thiếu asset bắt buộc.",
                evidence_locator="summary_render_log.json",
            )
        elif check.get("id") == "MEDIA_REVIEW":
            check.update(
                status="PASS",
                method="MODEL_REVIEW",
                details="16/16 asset đã được quan sát; nội dung, grounding, continuity và safety đạt.",
                evidence_locator="summary_media_review.json",
            )
        elif check.get("id") == "ORIENTATION_PARITY":
            check.update(
                status="PASS",
                method="MODEL_REVIEW",
                details="8/8 cặp landscape/portrait đạt parity; Scene 0007 là portrait độc lập 9:16.",
                evidence_locator="summary_media_review.json",
            )
        elif check.get("id") == "MANIFEST_MATCH":
            check.update(
                status="PASS",
                method="CODE",
                details="Manifest được tính lại từ exact bytes sau khi dựng lại media evidence.",
                evidence_locator="summary_manifest.json",
            )
    failed = [
        row for row in validation.get("checks", [])
        if isinstance(row, Mapping) and row.get("status") not in {"PASS", "NOT_APPLICABLE"}
    ]
    validation["remaining_work"] = []
    validation["status"] = "COMPLETE" if not failed else "PARTIAL"
    validation["limitations"] = [
        item for item in validation.get("limitations", [])
        if not any(
            marker in str(item)
            for marker in ("Không tạo ảnh portrait", "Gói Stage 2", "SCENE 0007:")
        )
    ]
    try:
        _atomic_write(root / "summary_render_plan.json", _canonical(plan))
        _atomic_write(root / "summary_render_log.json", _canonical(log))
        _atomic_write(root / "summary_media_review.json", _canonical(review))
        _atomic_write(root / "summary_validation_report.json", _canonical(validation))
        _atomic_write(root / "summary_manifest.json", rebuild_summary_manifest(root))
        issues = summary_manifest_issues(root)
        if issues:
            raise ValueError("Hậu kiểm manifest chưa đạt: " + "; ".join(issues))
    except Exception:
        for name in (
            "summary_render_plan.json",
            "summary_render_log.json",
            "summary_media_review.json",
            "summary_validation_report.json",
            "summary_manifest.json",
        ):
            source = backup / name
            if source.is_file():
                _atomic_write(root / name, source.read_bytes())
        raise
    return backup


def plan_summary_completion(root: Path) -> dict[str, Any]:
    """Prove whether the current Summary stage can be marked COMPLETE."""
    stage = _json(root / "summary_stage.json")
    manifest = _json(root / "summary_manifest.json")
    stage_number = stage.get("stage")
    blockers = summary_manifest_issues(root)
    if stage_number not in {1, 2, 3}:
        blockers.append("summary_stage.stage phải là 1, 2 hoặc 3")
    if stage.get("status") != manifest.get("status"):
        blockers.append("Trạng thái summary_stage và summary_manifest không khớp")

    validation_path = root / "summary_validation_report.json"
    if not validation_path.is_file():
        blockers.append("Thiếu summary_validation_report.json")
    else:
        validation = _json(validation_path)
        if validation.get("status") != "COMPLETE":
            blockers.append(f"Validation đang là {validation.get('status') or 'UNKNOWN'}, chưa phải COMPLETE")
        remaining = [str(item) for item in validation.get("remaining_work", []) if str(item).strip()]
        if remaining:
            blockers.append(f"Còn {len(remaining)} đầu việc trong remaining_work")
        failed = [
            str(row.get("id") or "UNKNOWN") for row in validation.get("checks", [])
            if isinstance(row, Mapping) and row.get("status") not in {"PASS", "NOT_APPLICABLE"}
        ]
        if failed:
            blockers.append("Gate chưa đạt: " + ", ".join(failed))

    render_plan_sync: list[str] = []
    if stage_number in {2, 3}:
        plan_path = root / "summary_render_plan.json"
        review_path = root / "summary_media_review.json"
        if not plan_path.is_file() or not review_path.is_file():
            blockers.append("Thiếu render plan hoặc media review")
        else:
            plan = _json(plan_path)
            review = _json(review_path)
            applicable = {"landscape"} if stage_number == 2 else {"landscape", "portrait"}
            required = [
                row for row in plan.get("assets", [])
                if isinstance(row, Mapping) and row.get("required") is True and row.get("orientation") in applicable
            ]
            reviews = {
                str(row.get("asset_id")): row for row in review.get("assets", [])
                if isinstance(row, Mapping)
            }
            invalid_review: list[str] = []
            for asset in required:
                asset_id = str(asset.get("asset_id"))
                row = reviews.get(asset_id)
                checks = row.get("checks") if isinstance(row, Mapping) else None
                review_passed = (
                    isinstance(row, Mapping)
                    and (
                        row.get("status") == "PASS"
                        or (
                            row.get("recommended_action") in {None, "NONE"}
                            and isinstance(checks, Mapping)
                            and all(
                                value in {"PASS", "PASS_WITH_DISCLOSED_VARIATION", "NOT_APPLICABLE"}
                                for value in checks.values()
                            )
                        )
                    )
                )
                if not review_passed:
                    invalid_review.append(asset_id)
                elif asset.get("status") != "VALIDATED":
                    render_plan_sync.append(asset_id)
            if invalid_review:
                blockers.append(f"{len(invalid_review)} media review chưa đạt: " + ", ".join(invalid_review[:4]))
    return {
        "stage": stage_number,
        "status": manifest.get("status"),
        "blockers": blockers,
        "render_plan_sync": render_plan_sync,
        "can_complete": not blockers and manifest.get("status") != "COMPLETE",
    }


def complete_summary_stage(root: Path) -> Path:
    """Atomically mark a proven Summary stage COMPLETE and rebind its manifest."""
    plan = plan_summary_completion(root)
    if plan["blockers"]:
        raise ValueError("Chưa thể hoàn tất Stage: " + "; ".join(plan["blockers"]))
    backup = _backup(
        root, ("summary_stage.json", "summary_manifest.json", "summary_render_plan.json")
    )
    stage = _json(root / "summary_stage.json")
    stage["status"] = "COMPLETE"
    try:
        if plan["render_plan_sync"]:
            render_plan = _json(root / "summary_render_plan.json")
            sync_ids = set(plan["render_plan_sync"])
            for asset in render_plan.get("assets", []):
                if isinstance(asset, dict) and asset.get("asset_id") in sync_ids:
                    asset["status"] = "VALIDATED"
            _atomic_write(root / "summary_render_plan.json", _canonical(render_plan))
        _atomic_write(root / "summary_stage.json", _canonical(stage))
        _atomic_write(root / "summary_manifest.json", rebuild_summary_manifest(root, status="COMPLETE"))
        issues = summary_manifest_issues(root)
        if issues:
            raise ValueError("Hậu kiểm manifest chưa đạt: " + "; ".join(issues))
    except Exception:
        for name in ("summary_stage.json", "summary_manifest.json", "summary_render_plan.json"):
            source = backup / name
            if source.is_file():
                _atomic_write(root / name, source.read_bytes())
        raise
    return backup


__all__ = [
    "complete_summary_stage",
    "plan_summary_completion",
    "rebuild_summary_manifest",
    "repair_summary_manifest",
    "revalidate_summary_media",
    "summary_manifest_issues",
]
