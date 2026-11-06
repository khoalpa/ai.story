"""Command-line entry points for Summary build, projection, audit, and migration."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Sequence

from studio.artifact_validation import strict_json_bytes
from studio.summary_audit import audit_summary_package
from studio.summary_media import load_media_root
from studio.summary_migration import migrate_summary_document
from studio.summary_package import (
    PROJECTION_TARGETS,
    build_summary_package,
    canonical_json_bytes,
    load_summary,
    write_projection_directory,
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
    except (OSError, ValueError) as exc:
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


__all__ = ["audit_main", "build_main", "migrate_main", "project_main"]
