"""Discover and validate selectable reference datasets."""
from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from studio.prompt_contract import PROJECT_ROOT
from studio.workflow_package import (
    MAX_PACKAGE_BYTES,
    inspect_directory,
    inspect_members,
    read_archive,
)

REFERENCE_ROOT = PROJECT_ROOT / "samples"
REFERENCE_REGISTRY_FILE = "registry.json"
REFERENCE_DATASET_FILE = "reference-set.json"
REFERENCE_CHECKSUM_FILE = "SHA256SUMS"
REFERENCE_SET_ENV = "AI_STORY_REFERENCE_SET"
LEGACY_REFERENCE_DIRECTORY = REFERENCE_ROOT / "Tiem_Sua_Nhung_Loi_Hua"
LEGACY_PACKAGE_STAGES = {
    "story_stage1.zip": "STAGE1", "story_stage2.zip": "STAGE2",
    "story.zip": "STAGE3", "story_video_prompts.zip": "STAGE4",
}


@dataclass(frozen=True)
class ReferenceDataset:
    set_id: str
    title: str
    directory: Path
    prompt_version: str
    packages: Mapping[str, str]
    tags: tuple[str, ...] = ()
    description: str = ""
    enabled: bool = True
    project_directory: str | None = None

    @property
    def label(self) -> str:
        return f"{self.title} ({self.set_id})"

    @property
    def package_names(self) -> tuple[str, ...]:
        return tuple(self.packages.values())


def _safe_child(root: Path, relative: str, *, field: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"{field} phải là đường dẫn tương đối không rỗng.")
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"{field} nằm ngoài thư mục samples: {relative!r}.")
    return resolved


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Không đọc được cấu hình bộ tham chiếu {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Cấu hình bộ tham chiếu phải là JSON object: {path}.")
    return value


def _parse_dataset(entry: Mapping[str, Any], root: Path) -> ReferenceDataset:
    set_id = str(entry.get("id") or entry.get("set_id") or "").strip().lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", set_id) is None:
        raise ValueError(f"set_id không hợp lệ: {set_id!r}.")
    directory = _safe_child(root, str(entry.get("path") or set_id), field="path")
    manifest_path = directory / REFERENCE_DATASET_FILE
    manifest = _read_json_object(manifest_path) if manifest_path.is_file() else dict(entry)
    declared_id = str(manifest.get("set_id") or set_id).strip().lower()
    if declared_id != set_id:
        raise ValueError(f"set_id trong {manifest_path} không khớp registry.")
    raw_packages = manifest.get("packages") or {}
    if not isinstance(raw_packages, dict):
        raise ValueError(f"packages phải là object trong {manifest_path}.")
    packages: dict[str, str] = {}
    for stage, filename in raw_packages.items():
        normalized_stage = str(stage).upper()
        if normalized_stage not in {"STAGE1", "STAGE2", "STAGE3", "STAGE4"}:
            raise ValueError(f"Giai đoạn không hợp lệ trong {manifest_path}: {stage!r}.")
        path = _safe_child(directory, str(filename), field=f"packages.{normalized_stage}")
        packages[normalized_stage] = path.relative_to(directory.resolve()).as_posix()
    raw_tags = manifest.get("tags") or []
    if not isinstance(raw_tags, list) or not all(isinstance(tag, str) for tag in raw_tags):
        raise ValueError(f"tags phải là danh sách chuỗi trong {manifest_path}.")
    project_directory = manifest.get("project_directory")
    if project_directory is not None:
        project_directory = str(project_directory)
        _safe_child(directory, project_directory, field="project_directory")
    if not packages and project_directory is None:
        raise ValueError(f"Bộ {set_id!r} phải có packages hoặc project_directory.")
    return ReferenceDataset(
        set_id=set_id, title=str(manifest.get("title") or set_id), directory=directory,
        prompt_version=str(manifest.get("prompt_version") or "4.1.6"), packages=packages,
        tags=tuple(raw_tags), description=str(manifest.get("description") or ""),
        enabled=bool(entry.get("enabled", manifest.get("enabled", True))),
        project_directory=project_directory,
    )


def load_reference_registry(root: Path = REFERENCE_ROOT) -> tuple[tuple[ReferenceDataset, ...], str]:
    path = root / REFERENCE_REGISTRY_FILE
    document = _read_json_object(path)
    if document.get("schema_version") != 1:
        raise ValueError(f"schema_version của {path} phải bằng 1.")
    entries = document.get("sets")
    if not isinstance(entries, list) or not entries or not all(isinstance(row, dict) for row in entries):
        raise ValueError(f"{path} phải khai báo danh sách bộ tham chiếu.")
    datasets = tuple(_parse_dataset(entry, root) for entry in entries)
    ids = [dataset.set_id for dataset in datasets]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path} chứa set_id trùng nhau.")
    default = str(document.get("default_set") or "").strip().lower()
    if default not in {dataset.set_id for dataset in datasets if dataset.enabled}:
        raise ValueError(f"default_set {default!r} không tồn tại hoặc đã bị tắt.")
    return datasets, default


def discover_reference_datasets(root: Path = REFERENCE_ROOT) -> tuple[ReferenceDataset, ...]:
    datasets, _default = load_reference_registry(root)
    return tuple(dataset for dataset in datasets if dataset.enabled)


def get_reference_dataset(set_id: str | None = None, *, root: Path = REFERENCE_ROOT) -> ReferenceDataset:
    datasets, default = load_reference_registry(root)
    requested = (set_id or os.environ.get(REFERENCE_SET_ENV) or default).strip().lower()
    for dataset in datasets:
        if dataset.enabled and dataset.set_id == requested:
            return dataset
    available = ", ".join(dataset.set_id for dataset in datasets if dataset.enabled)
    raise ValueError(f"Không có bộ tham chiếu {requested!r}. Các bộ khả dụng: {available}.")


def reference_checksums(directory: Path = LEGACY_REFERENCE_DIRECTORY) -> dict[str, str]:
    path = directory / REFERENCE_CHECKSUM_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"Thiếu danh sách checksum mẫu: {path}.") from exc
    hashes: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+\.zip)", line)
        if match is None or match[2] in hashes:
            raise ValueError(f"Danh sách checksum mẫu không hợp lệ hoặc trùng tên: {path}.")
        hashes[match[2]] = match[1]
    return hashes


def load_dataset_package(dataset: ReferenceDataset, stage: str) -> tuple[dict[str, bytes], dict[str, Any]]:
    normalized_stage = stage.upper()
    try:
        filename = dataset.packages[normalized_stage]
    except KeyError as exc:
        raise ValueError(f"Bộ {dataset.set_id!r} không có gói {normalized_stage}.") from exc
    path = _safe_child(dataset.directory, filename, field=f"packages.{normalized_stage}")
    expected = reference_checksums(dataset.directory).get(path.name)
    if expected is None:
        raise ValueError(f"Thiếu checksum cho ZIP mẫu: {path.name}.")
    try:
        if path.stat().st_size > MAX_PACKAGE_BYTES:
            raise ValueError(f"ZIP mẫu vượt giới hạn dung lượng: {path}.")
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(
            f"Không đọc được ZIP mẫu {path.name} trong thư mục samples: {path.parent}."
        ) from exc
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Checksum ZIP mẫu không khớp: {path}.")
    try:
        members = read_archive(raw)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError(f"ZIP mẫu không đọc được: {path}: {exc}") from exc
    result = inspect_members(members, archive=True)
    if result.get("status") != "PASS" or result.get("stage") != normalized_stage:
        raise ValueError(f"ZIP mẫu {path} không đạt hợp đồng {normalized_stage}.")
    return members, result


def validate_reference_dataset(dataset: ReferenceDataset) -> dict[str, Any]:
    package_results: dict[str, Any] = {}
    errors: list[str] = []
    for stage in dataset.packages:
        try:
            _members, result = load_dataset_package(dataset, stage)
            package_results[stage] = result
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    project_result: dict[str, Any] | None = None
    if dataset.project_directory is not None:
        project_path = _safe_child(dataset.directory, dataset.project_directory, field="project_directory")
        try:
            project_result = inspect_directory(project_path)
            if project_result.get("status") != "PASS":
                errors.append(f"Project {project_path} không đạt hợp đồng hiện hành.")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    return {"set_id": dataset.set_id, "title": dataset.title,
            "status": "PASS" if not errors else "FAIL", "packages": package_results,
            "project": project_result, "errors": errors}


# Compatibility layer for callers using the former fixed four-archive API.
REFERENCE_PACKAGE_DIRECTORY = LEGACY_REFERENCE_DIRECTORY
REFERENCE_PACKAGE_STAGES = LEGACY_PACKAGE_STAGES
REFERENCE_PACKAGE_NAMES = tuple(LEGACY_PACKAGE_STAGES)


def load_reference_package(name: str, directory: Path = REFERENCE_PACKAGE_DIRECTORY) -> tuple[dict[str, bytes], dict[str, Any]]:
    if name not in LEGACY_PACKAGE_STAGES:
        raise ValueError(f"Không có gói mẫu chuẩn mang tên {name!r}.")
    dataset = ReferenceDataset(
        set_id="legacy", title="Legacy", directory=directory, prompt_version="4.1.6",
        packages={stage: filename for filename, stage in LEGACY_PACKAGE_STAGES.items()},
    )
    return load_dataset_package(dataset, LEGACY_PACKAGE_STAGES[name])
