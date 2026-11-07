"""Three-stage Summary production workflow with immutable package lineage."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from studio.artifact_validation import strict_json_bytes
from studio.summary_audit import audit_summary_package, load_summary_members
from studio.summary_media import default_render_config, load_media_root
from studio.summary_package import build_summary_package


def build_summary_stage1(
    summary: Mapping[str, Any],
    output: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Create canonical content, projections, Scene plan, and render queue."""
    return build_summary_package(
        summary,
        output,
        overwrite=overwrite,
        include_media_workflow=False,
        stage=1,
    )


def build_summary_stage2(
    stage1: Path,
    output: Path,
    media_root: Path,
    media_review: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> Path:
    """Create and validate all required landscape images from Stage 1."""
    members, parent_hash = _load_complete_stage(stage1, expected_stage=1)
    config = default_render_config()
    return build_summary_package(
        strict_json_bytes(members["summary.json"]),
        output,
        overwrite=overwrite,
        summary_visual_plan=strict_json_bytes(members["summary_visual_plan.json"]),
        media=load_media_root(media_root),
        media_review=media_review,
        render_config=config,
        stage=2,
        parent_package_sha256=parent_hash,
    )


def build_summary_stage3(
    stage2: Path,
    output: Path,
    media_root: Path,
    media_review: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> Path:
    """Add required portrait images, validate parity, and create the final package."""
    members, parent_hash = _load_complete_stage(stage2, expected_stage=2)
    inherited_media = {
        name: raw
        for name, raw in members.items()
        if name.startswith(("landscape/", "portrait/"))
    }
    inherited_media.update(load_media_root(media_root))
    config = default_render_config()
    config["required_orientations"] = ["landscape", "portrait"]
    config["optional_orientations"] = []
    return build_summary_package(
        strict_json_bytes(members["summary.json"]),
        output,
        overwrite=overwrite,
        summary_visual_plan=strict_json_bytes(members["summary_visual_plan.json"]),
        media=inherited_media,
        media_review=media_review,
        render_config=config,
        stage=3,
        parent_package_sha256=parent_hash,
    )


def _load_complete_stage(
    path: Path, *, expected_stage: int
) -> tuple[dict[str, bytes], str]:
    audit = audit_summary_package(path)
    if audit.status != "PASS":
        raise ValueError("Stage nguồn không đạt audit: " + "; ".join(audit.errors))
    members = load_summary_members(path)
    stage = strict_json_bytes(members.get("summary_stage.json", b""))
    manifest = strict_json_bytes(members.get("summary_manifest.json", b""))
    if stage.get("stage") != expected_stage:
        raise ValueError(f"Yêu cầu Stage {expected_stage} làm đầu vào")
    if stage.get("status") != "COMPLETE" or manifest.get("status") != "COMPLETE":
        raise ValueError(f"Stage {expected_stage} chưa COMPLETE")
    return members, hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["build_summary_stage1", "build_summary_stage2", "build_summary_stage3"]
