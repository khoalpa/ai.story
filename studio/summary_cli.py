"""Command-line entry points for Summary build, projection, audit, and migration."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Sequence

from studio.artifact_validation import strict_json_bytes
from studio.summary_audit import audit_summary_package
from studio.summary_image_generation import render_summary_package
from studio.summary_image_provider import CommandImageProvider
from studio.summary_media import load_media_root
from studio.summary_migration import migrate_summary_document
from studio.summary_package import (
    PROJECTION_TARGETS,
    build_summary_package,
    canonical_json_bytes,
    load_summary,
    write_projection_directory,
)
from studio.summary_stages import (
    build_summary_stage1,
    build_summary_stage2,
    build_summary_stage3,
)


def _stdout(value: object) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and audit a deterministic Summary ZIP package."
    )
    parser.add_argument("summary", type=Path, help="Canonical summary.json")
    parser.add_argument(
        "--output", type=Path, required=True, help="Output summary_package.zip"
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=PROJECTION_TARGETS,
        default=list(PROJECTION_TARGETS),
    )
    parser.add_argument(
        "--media-root", type=Path, help="Thư mục chứa landscape/ và portrait/"
    )
    parser.add_argument(
        "--media-review", type=Path, help="JSON xác nhận kiểm định nội dung ảnh"
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        media = load_media_root(args.media_root) if args.media_root else None
        review = (
            strict_json_bytes(args.media_review.read_bytes())
            if args.media_review
            else None
        )
        output = build_summary_package(
            load_summary(args.summary),
            args.output,
            args.targets,
            overwrite=args.overwrite,
            media=media,
            media_review=review,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    with zipfile.ZipFile(output) as archive:
        status = json.loads(archive.read("summary_manifest.json"))["status"]
    _stdout({"status": status, "package": str(output)})
    return 0


def project_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project summary.json into Story/Audio/Video artifacts."
    )
    parser.add_argument("summary", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=PROJECTION_TARGETS,
        default=list(PROJECTION_TARGETS),
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        written = write_projection_directory(
            load_summary(args.summary),
            args.output,
            args.targets,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    _stdout({"status": "COMPLETE", "files": [str(path) for path in written]})
    return 0


def audit_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit a Summary directory or ZIP package."
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    result = audit_summary_package(args.path)
    _stdout(result.as_dict())
    return 1 if result.status == "FAIL" else 0


def migrate_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate a Summary document to the current schema."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists() and not args.overwrite:
        parser.error(f"Tệp đã tồn tại: {args.output}")
    try:
        source = strict_json_bytes(args.source.read_bytes())
        migrated = migrate_summary_document(source)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical_json_bytes(migrated))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    _stdout(
        {"status": "COMPLETE", "output": str(args.output), "schema_version": "1.1.0"}
    )
    return 0


def stage1_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Summary Stage 1 canonical package."
    )
    parser.add_argument("summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = build_summary_stage1(
            load_summary(args.summary), args.output, overwrite=args.overwrite
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    _stdout({"status": "COMPLETE", "stage": 1, "package": str(output)})
    return 0


def _media_stage_main(
    stage: int,
    builder: Any,
    argv: Sequence[str] | None,
) -> int:
    parser = argparse.ArgumentParser(
        description=f"Build Summary Stage {stage} media package."
    )
    parser.add_argument("source", type=Path, help=f"Stage {stage - 1} COMPLETE ZIP")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--media-review", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        review = strict_json_bytes(args.media_review.read_bytes())
        output = builder(
            args.source,
            args.output,
            args.media_root,
            review,
            overwrite=args.overwrite,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    with zipfile.ZipFile(output) as archive:
        status = json.loads(archive.read("summary_manifest.json"))["status"]
    _stdout({"status": status, "stage": stage, "package": str(output)})
    return 0


def stage2_main(argv: Sequence[str] | None = None) -> int:
    return _media_stage_main(2, build_summary_stage2, argv)


def stage3_main(argv: Sequence[str] | None = None) -> int:
    return _media_stage_main(3, build_summary_stage3, argv)


def render_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Summary images through an explicit provider adapter."
    )
    parser.add_argument("source", type=Path, help="Audited Summary stage ZIP")
    parser.add_argument("--output", type=Path, required=True, help="Media output root")
    parser.add_argument(
        "--orientation", choices=("landscape", "portrait"), required=True
    )
    parser.add_argument(
        "--provider-executable",
        required=True,
        help="Adapter executable: JSON request on stdin, image bytes on stdout",
    )
    parser.add_argument(
        "--provider-arg", action="append", default=[], help="Repeatable adapter argument"
    )
    parser.add_argument("--provider-name", default="command")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--pilot-count", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        provider = CommandImageProvider(
            [args.provider_executable, *args.provider_arg],
            timeout_seconds=args.timeout,
            provider_name=args.provider_name,
        )
        result = render_summary_package(
            args.source,
            args.output,
            provider,
            orientation=args.orientation,
            max_attempts=args.max_attempts,
            pilot_count=args.pilot_count,
            overwrite=args.overwrite,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    _stdout(
        {
            "status": result.status,
            "output": str(result.output_root),
            "orientation": args.orientation,
            "generated": result.generated,
            "failed": result.failed,
            "media_review": str(result.media_review_path),
        }
    )
    return 0 if result.status == "COMPLETE" else 1


__all__ = [
    "audit_main",
    "build_main",
    "migrate_main",
    "project_main",
    "render_main",
    "stage1_main",
    "stage2_main",
    "stage3_main",
]
