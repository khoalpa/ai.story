"""Strict Video-module support for Audio Story packages authored by v4.1.6.

The authoring prompt version is 4.1.6 and the public JSON schema version is
4.1.3.  Packages are verified before any paths are exposed to the renderer.
There is intentionally no legacy-package adapter in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from studio.workflow_package import inspect_directory, inspect_members, read_archive

SCHEMA_VERSION = "4.1.3"
PROMPT_VERSION = "4.1.6"
SUPPORTED_STAGES = {"STAGE1", "STAGE2", "STAGE3", "STAGE4"}
VIDEO_READY_STAGES = {"STAGE2", "STAGE3", "STAGE4"}


@dataclass(frozen=True)
class VideoPackageInputs:
    """Verified files from an extracted v4.1.6 package."""

    root: Path
    stage: str
    story_json: Path
    validation_report_json: Path
    manifest_json: Path
    visual_plan_json: Path | None
    video_prompts_json: Path | None
    landscape_dir: Path | None
    portrait_dir: Path | None

    def scenes_dir(self, aspect: str) -> Path:
        normalized = str(aspect).casefold().replace(":", "x")
        directory = self.landscape_dir if normalized in {"16x9", "landscape"} else self.portrait_dir
        if directory is None:
            raise ValueError(
                f"Gói {self.stage} chưa có bộ ảnh cho tỷ lệ {aspect}; "
                "Video cần gói Stage 2 trở lên cho ảnh ngang hoặc Stage 3 trở lên cho ảnh dọc."
            )
        return directory

    def cover(self, aspect: str) -> Path:
        path = self.scenes_dir(aspect) / "cover.png"
        if not path.is_file():
            raise ValueError(f"Gói v4.1.6 thiếu ảnh bìa đã khai báo: {path}")
        return path


def _failure_details(inspection: Mapping[str, Any]) -> str:
    details = [
        str(row.get("detail") or "").strip()
        for row in inspection.get("checks", [])
        if isinstance(row, Mapping) and row.get("status") != "PASS"
    ]
    return "; ".join(item for item in details if item) or "manifest/file set không đạt"


def _require_current(inspection: Mapping[str, Any], *, source: str) -> None:
    if (
        inspection.get("compatibility") != "NATIVE_CURRENT"
        or inspection.get("status") != "PASS"
        or inspection.get("stage") not in SUPPORTED_STAGES
    ):
        raise ValueError(
            f"{source} không phải gói v4.1.6 hợp lệ; gói cũ không được hỗ trợ: "
            f"{_failure_details(inspection)}"
        )
    manifest = inspection.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError(f"{source} thiếu manifest.json v4.1.6 hợp lệ.")
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("prompt_version") != PROMPT_VERSION:
        raise ValueError(
            f"{source} phải dùng schema {SCHEMA_VERSION} và prompt {PROMPT_VERSION}; "
            "gói cũ không được hỗ trợ."
        )


def inspect_package_bytes(raw: bytes) -> dict[str, Any]:
    """Open and fully verify a ZIP without extracting it."""
    try:
        inspection = inspect_members(read_archive(raw), archive=True)
    except Exception as exc:
        raise ValueError(f"ZIP không phải gói v4.1.6 hợp lệ: {exc}") from exc
    _require_current(inspection, source="ZIP")
    return inspection


def load_package_bytes(raw: bytes) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Return verified ZIP members and inspection metadata.

    Bytes are returned only after path safety, CRC, manifest, size and SHA-256
    checks have passed.  Callers must not infer support from filenames alone.
    """
    try:
        members = read_archive(raw)
        inspection = inspect_members(members, archive=True)
    except Exception as exc:
        raise ValueError(f"ZIP không phải gói v4.1.6 hợp lệ: {exc}") from exc
    _require_current(inspection, source="ZIP")
    return members, inspection


def inspect_project_directory(root: Path) -> dict[str, Any]:
    """Verify an extracted package directory without legacy fallback."""
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Thư mục gói không tồn tại: {path}")
    try:
        inspection = inspect_directory(path)
    except Exception as exc:
        raise ValueError(f"Thư mục không phải gói v4.1.6 hợp lệ: {exc}") from exc
    _require_current(inspection, source="Thư mục")
    return inspection


def load_project_directory(root: Path) -> tuple[VideoPackageInputs, dict[str, Any]]:
    """Verify an extracted package and resolve its canonical Video inputs."""
    path = Path(root).expanduser().resolve()
    inspection = inspect_project_directory(path)
    stage = str(inspection["stage"])

    visual_plan = path / "visual_plan.json"
    video_prompts = path / "video_prompts.json"
    landscape = path / "landscape"
    portrait = path / "portrait"
    inputs = VideoPackageInputs(
        root=path,
        stage=stage,
        story_json=path / "story.json",
        validation_report_json=path / "validation_report.json",
        manifest_json=path / "manifest.json",
        visual_plan_json=visual_plan if visual_plan.is_file() else None,
        video_prompts_json=video_prompts if video_prompts.is_file() else None,
        landscape_dir=landscape if landscape.is_dir() else None,
        portrait_dir=portrait if portrait.is_dir() else None,
    )
    return inputs, inspection


__all__ = [
    "PROMPT_VERSION", "SCHEMA_VERSION", "SUPPORTED_STAGES", "VIDEO_READY_STAGES",
    "VideoPackageInputs", "inspect_package_bytes", "inspect_project_directory",
    "load_package_bytes", "load_project_directory",
]
