"""Deterministic Summary projection and package construction."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from studio.artifact_validation import strict_json_bytes
from studio.summary_audit import audit_summary_package
from studio.summary_media import (
    build_render_plan,
    finalize_render_plan,
    inspect_rendered_media,
)
from studio.summary_projection import (
    project_summary_to_image_prompts,
    project_summary_to_story,
    project_summary_to_video_prompts,
    project_summary_to_visual_plan,
)
from studio.summary_schema import validate_summary_document
from studio.summary_visual import build_summary_visual_plan

PROJECTION_TARGETS = ("story", "visual", "image", "video")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def load_summary(path: Path) -> dict[str, Any]:
    document = dict(strict_json_bytes(path.read_bytes()))
    errors = validate_summary_document(document)
    if errors:
        raise ValueError("summary.json không hợp lệ: " + "; ".join(errors))
    return document


def project_summary_artifacts(
    summary: Mapping[str, Any],
    targets: Sequence[str] = PROJECTION_TARGETS,
    summary_visual_plan: Mapping[str, Any] | None = None,
) -> dict[str, bytes]:
    unknown = set(targets) - set(PROJECTION_TARGETS)
    if unknown:
        raise ValueError(
            "Projection target không hỗ trợ: " + ", ".join(sorted(unknown))
        )
    errors = validate_summary_document(summary)
    if errors:
        raise ValueError("summary.json không hợp lệ: " + "; ".join(errors))
    requested = set(targets)
    if requested & {"visual", "image", "video"}:
        requested.add("story")
    story = project_summary_to_story(summary) if "story" in requested else None
    files: dict[str, bytes] = {}
    if story is not None:
        files["story.json"] = canonical_json_bytes(story)
    visual = None
    if "visual" in requested or "image" in requested:
        assert story is not None
        summary_visual = (
            dict(summary_visual_plan)
            if summary_visual_plan is not None
            else build_summary_visual_plan(summary)
        )
        files["summary_visual_plan.json"] = canonical_json_bytes(summary_visual)
        visual = project_summary_to_visual_plan(summary, story, summary_visual)
        files["visual_plan.json"] = canonical_json_bytes(visual)
    if "image" in requested:
        assert story is not None and visual is not None
        files["image_prompts.json"] = canonical_json_bytes(
            project_summary_to_image_prompts(summary, story, visual)
        )
        assert summary_visual is not None
        files["summary_render_plan.json"] = canonical_json_bytes(
            build_render_plan(summary, summary_visual)
        )
    if "video" in requested:
        assert story is not None
        files["video_prompts.json"] = canonical_json_bytes(
            project_summary_to_video_prompts(summary, story)
        )
    return files


def projection_report(summary_raw: bytes, files: Mapping[str, bytes]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "prompt_version": "1.5.0",
        "source_summary_sha256": hashlib.sha256(summary_raw).hexdigest(),
        "status": "COMPLETE",
        "artifacts": [
            {
                "path": name,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            for name, raw in sorted(files.items())
        ],
        "validators": [
            "validate_summary_document",
            "validate_story_document",
            "validate_visual_plan",
            "validate_image_prompt_plan",
            "validate_v5_plan",
        ],
        "limitations": [],
    }


def build_summary_members(
    summary: Mapping[str, Any],
    targets: Sequence[str] = PROJECTION_TARGETS,
    summary_visual_plan: Mapping[str, Any] | None = None,
    media: Mapping[str, bytes] | None = None,
    render_config: Mapping[str, Any] | None = None,
    media_review: Mapping[str, Any] | None = None,
    *,
    include_media_workflow: bool = True,
    stage: int | None = None,
    parent_package_sha256: str | None = None,
) -> dict[str, bytes]:
    summary_raw = canonical_json_bytes(summary)
    files: dict[str, bytes] = {"summary.json": summary_raw}
    projected = project_summary_artifacts(summary, targets, summary_visual_plan)
    files.update(projected)
    package_status = "COMPLETE"
    media_paths: set[str] = set()
    if "image" in targets and include_media_workflow:
        visual_plan = (
            dict(summary_visual_plan)
            if summary_visual_plan is not None
            else build_summary_visual_plan(summary)
        )
        render_plan = build_render_plan(summary, visual_plan, render_config)
        render_log, review, package_status = inspect_rendered_media(
            render_plan, media or {}, media_review
        )
        render_plan = finalize_render_plan(render_plan, review)
        files["summary_render_plan.json"] = canonical_json_bytes(render_plan)
        files["summary_render_log.json"] = canonical_json_bytes(render_log)
        files["summary_media_review.json"] = canonical_json_bytes(review)
        for name, raw in sorted((media or {}).items()):
            if not (name.startswith("landscape/") or name.startswith("portrait/")):
                raise ValueError(
                    f"Media phải nằm trong landscape/ hoặc portrait/: {name}"
                )
            files[name] = raw
            media_paths.add(name)
    if stage is not None:
        if stage not in {1, 2, 3}:
            raise ValueError("Summary stage phải là 1, 2 hoặc 3")
        files["summary_stage.json"] = canonical_json_bytes(
            {
                "schema_version": "1.0.0",
                "prompt_version": "1.5.0",
                "stage": stage,
                "parent_package_sha256": parent_package_sha256,
                "status": package_status,
            }
        )
    files["projection_report.json"] = canonical_json_bytes(
        projection_report(summary_raw, projected)
    )
    manifest = {
        "schema_version": "1.1.0",
        "prompt_version": "1.5.0",
        "status": package_status,
        "parent_package_sha256": parent_package_sha256,
        "source_fingerprints": [
            {
                "source_id": row["source_id"],
                "sha256": row.get("sha256"),
                "size_bytes": row.get("size_bytes"),
            }
            for row in summary["sources"]
        ],
        "files": [
            _manifest_row(
                name, raw, media_paths, files.get("summary_media_review.json")
            )
            for name, raw in sorted(files.items())
        ],
    }
    files["summary_manifest.json"] = canonical_json_bytes(manifest)
    return files


def write_projection_directory(
    summary: Mapping[str, Any],
    output: Path,
    targets: Sequence[str] = PROJECTION_TARGETS,
    *,
    overwrite: bool = False,
) -> tuple[Path, ...]:
    output.mkdir(parents=True, exist_ok=True)
    files = project_summary_artifacts(summary, targets)
    written: list[Path] = []
    for name, raw in files.items():
        destination = output / name
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Tệp đã tồn tại: {destination}")
        destination.write_bytes(raw)
        written.append(destination)
    return tuple(written)


def build_summary_package(
    summary: Mapping[str, Any],
    output: Path,
    targets: Sequence[str] = PROJECTION_TARGETS,
    *,
    overwrite: bool = False,
    summary_visual_plan: Mapping[str, Any] | None = None,
    media: Mapping[str, bytes] | None = None,
    render_config: Mapping[str, Any] | None = None,
    media_review: Mapping[str, Any] | None = None,
    include_media_workflow: bool = True,
    stage: int | None = None,
    parent_package_sha256: str | None = None,
) -> Path:
    if output.exists() and not overwrite:
        raise FileExistsError(f"Tệp đã tồn tại: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    members = build_summary_members(
        summary,
        targets,
        summary_visual_plan,
        media,
        render_config,
        media_review,
        include_media_workflow=include_media_workflow,
        stage=stage,
        parent_package_sha256=parent_package_sha256,
    )
    handle, temporary_name = tempfile.mkstemp(
        prefix=".summary-package-", suffix=".zip", dir=output.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name, raw in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, raw)
        audit = audit_summary_package(temporary)
        if audit.status != "PASS":
            raise ValueError(
                "Package sau đóng gói không đạt audit: " + "; ".join(audit.errors)
            )
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def build_summary_package_bytes(
    summary: Mapping[str, Any],
    targets: Sequence[str] = PROJECTION_TARGETS,
    summary_visual_plan: Mapping[str, Any] | None = None,
    media: Mapping[str, bytes] | None = None,
    render_config: Mapping[str, Any] | None = None,
    media_review: Mapping[str, Any] | None = None,
    *,
    include_media_workflow: bool = True,
    stage: int | None = None,
    parent_package_sha256: str | None = None,
) -> bytes:
    with tempfile.TemporaryDirectory(prefix="ai-summary-package-") as temporary:
        path = Path(temporary) / "summary_package.zip"
        build_summary_package(
            summary,
            path,
            targets,
            summary_visual_plan=summary_visual_plan,
            media=media,
            render_config=render_config,
            media_review=media_review,
            include_media_workflow=include_media_workflow,
            stage=stage,
            parent_package_sha256=parent_package_sha256,
        )
        return path.read_bytes()


def _manifest_row(
    name: str,
    raw: bytes,
    media_paths: set[str],
    review_raw: bytes | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": name,
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "origin": "summary" if name == "summary.json" else "summary_projection",
    }
    if name not in media_paths:
        return row
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(raw)) as image:
        width, height = image.size
        media_type = Image.MIME.get(image.format, "application/octet-stream")
    reviews = json.loads(review_raw or b"{}").get("assets", [])
    review: dict[str, Any] = next(
        (item for item in reviews if item.get("path") == name), {}
    )
    stem = Path(name).stem
    row.update(
        {
            "origin": "generated",
            "asset_id": review.get("asset_id"),
            "scene_id": review.get("scene_id", stem),
            "orientation": name.split("/", 1)[0],
            "media_type": media_type,
            "width": width,
            "height": height,
            "review_status": review.get("status", "PENDING_REVIEW"),
        }
    )
    return row


__all__ = [
    "PROJECTION_TARGETS",
    "build_summary_members",
    "build_summary_package",
    "build_summary_package_bytes",
    "canonical_json_bytes",
    "load_summary",
    "project_summary_artifacts",
    "projection_report",
    "write_projection_directory",
]
