"""Discover and validate selectable reference datasets."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
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


@dataclass(frozen=True)
class ReferenceRegistry:
    """Usable datasets plus non-fatal errors from individual registry entries."""

    datasets: tuple[ReferenceDataset, ...]
    default_set: str | None
    warnings: tuple[str, ...] = ()
    registered_count: int = 0
    discovered_count: int = 0
    duplicate_count: int = 0
    ignored_directory_count: int = 0


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


def _project_identity(directory: Path) -> tuple[str, str, tuple[str, ...]]:
    """Derive stable display metadata for a canonical project without a sidecar."""
    folder_name = directory.name.strip()
    match = re.match(r"^\[([A-Za-z0-9._-]+)\]\s*(.+)$", folder_name)
    declared_id = match.group(1).lower() if match else ""
    title = match.group(2).strip() if match else folder_name

    episode_match = re.search(r"(?i)(?:^|\s|[-–—])tập\s+(\d+)(?:\s|[-–—]|$)", title)
    if episode_match and declared_id:
        prefix_match = re.match(r"^(.+?)-\d+$", declared_id)
        if prefix_match:
            declared_id = f"{prefix_match.group(1)}-{int(episode_match.group(1)):04d}"

    if not declared_id:
        ascii_name = unicodedata.normalize("NFKD", folder_name).encode("ascii", "ignore").decode("ascii")
        declared_id = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:64]
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", declared_id) is None:
        raise ValueError(f"Không thể suy ra set_id hợp lệ từ tên thư mục {folder_name!r}.")
    tag = declared_id.split("-", 1)[0]
    return declared_id, title, (tag,) if tag else ()


def _discover_project_dataset(directory: Path) -> tuple[ReferenceDataset, dict[str, Any]]:
    """Create in-memory dataset metadata from a canonical project directory."""
    manifest_path = directory / "manifest.json"
    manifest = _read_json_object(manifest_path)
    prompt_version = str(manifest.get("prompt_version") or "").strip()
    if not prompt_version:
        raise ValueError(f"Thiếu prompt_version trong {manifest_path}.")
    if not isinstance(manifest.get("files"), list):
        raise ValueError(f"manifest.files phải là array trong {manifest_path}.")
    set_id, title, tags = _project_identity(directory)
    result = inspect_directory(directory)
    if result.get("compatibility") == "UNSUPPORTED":
        raise ValueError(f"Project {directory} dùng schema hoặc prompt không được hỗ trợ.")
    return ReferenceDataset(
        set_id=set_id,
        title=title,
        directory=directory.resolve(),
        prompt_version=prompt_version,
        packages={},
        tags=tags,
        description="Tự phát hiện từ manifest.json.",
        project_directory=".",
    ), result


def suggest_reference_metadata(project_directory: Path) -> dict[str, Any]:
    """Suggest sidecar metadata from a canonical project without mutating it."""
    project_directory = project_directory.resolve()
    existing = project_directory / REFERENCE_DATASET_FILE
    if existing.is_file():
        return _read_json_object(existing)
    manifest = _read_json_object(project_directory / "manifest.json")
    prompt_version = str(manifest.get("prompt_version") or "").strip()
    if not prompt_version:
        raise ValueError("Không thể đề xuất metadata vì manifest thiếu prompt_version.")
    set_id, title, tags = _project_identity(project_directory)
    return {
        "schema_version": 1,
        "set_id": set_id,
        "title": title,
        "prompt_version": prompt_version,
        "project_directory": ".",
        "tags": list(tags),
    }


def validate_reference_metadata(
    metadata: Mapping[str, Any], project_directory: Path, *, root: Path = REFERENCE_ROOT,
) -> dict[str, Any]:
    """Normalize sidecar metadata and reject unsafe paths or conflicting IDs."""
    resolved_root = root.resolve()
    resolved_project = project_directory.resolve()
    if resolved_project.parent != resolved_root:
        raise ValueError("Bộ mẫu phải là thư mục con trực tiếp của samples.")
    set_id = str(metadata.get("set_id") or "").strip().lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", set_id) is None:
        raise ValueError(f"set_id không hợp lệ: {set_id!r}.")
    title = str(metadata.get("title") or "").strip()
    prompt_version = str(metadata.get("prompt_version") or "").strip()
    if not title or not prompt_version:
        raise ValueError("title và prompt_version không được để trống.")
    raw_tags = metadata.get("tags") or []
    if not isinstance(raw_tags, list) or not all(isinstance(tag, str) for tag in raw_tags):
        raise ValueError("tags phải là danh sách chuỗi.")
    tags = [tag.strip() for tag in raw_tags if tag.strip()]
    if len(tags) != len(set(tags)):
        raise ValueError("tags không được trùng nhau.")

    normalized: dict[str, Any] = {
        "schema_version": 1,
        "set_id": set_id,
        "title": title,
        "prompt_version": prompt_version,
    }
    raw_packages = metadata.get("packages")
    project_relative = metadata.get("project_directory")
    if raw_packages:
        if not isinstance(raw_packages, dict):
            raise ValueError("packages phải là object.")
        normalized["packages"] = dict(raw_packages)
    elif project_relative is not None:
        relative = str(project_relative)
        _safe_child(resolved_project, relative, field="project_directory")
        normalized["project_directory"] = relative
    else:
        raise ValueError("Metadata phải có packages hoặc project_directory.")
    if tags:
        normalized["tags"] = tags

    registry = load_reference_registry_tolerant(root)
    conflict = next(
        (
            dataset for dataset in registry.datasets
            if dataset.set_id == set_id and dataset.directory.resolve() != resolved_project
        ),
        None,
    )
    if conflict is not None:
        raise ValueError(f"set_id {set_id!r} đã được dùng tại {conflict.directory}.")
    return normalized


def write_reference_sidecar(
    project_directory: Path,
    metadata: Mapping[str, Any],
    *,
    root: Path = REFERENCE_ROOT,
    overwrite: bool = False,
) -> Path:
    """Atomically create or update reference-set.json outside canonical payloads."""
    project_directory = project_directory.resolve()
    destination = project_directory / REFERENCE_DATASET_FILE
    if destination.exists() and not overwrite:
        raise ValueError(f"{REFERENCE_DATASET_FILE} đã tồn tại; hãy dùng chế độ chỉnh sửa.")
    normalized = validate_reference_metadata(metadata, project_directory, root=root)
    payload = (json.dumps(normalized, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=project_directory, delete=False, suffix=".tmp") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        _read_json_object(temporary)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def delete_reference_sidecar(project_directory: Path, *, root: Path = REFERENCE_ROOT) -> None:
    """Delete only the dataset sidecar, leaving the project and packages untouched."""
    project_directory = project_directory.resolve()
    if project_directory.parent != root.resolve():
        raise ValueError("Bộ mẫu phải là thư mục con trực tiếp của samples.")
    path = project_directory / REFERENCE_DATASET_FILE
    if not path.is_file():
        raise ValueError(f"Không tìm thấy {REFERENCE_DATASET_FILE}.")
    path.unlink()


def _parse_dataset(entry: Mapping[str, Any], root: Path) -> ReferenceDataset:
    set_id = str(entry.get("id") or entry.get("set_id") or "").strip().lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", set_id) is None:
        raise ValueError(f"set_id không hợp lệ: {set_id!r}.")
    directory = _safe_child(root, str(entry.get("path") or set_id), field="path")
    if not directory.is_dir():
        raise ValueError(f"Không tìm thấy thư mục của bộ {set_id!r}: {directory}.")
    manifest_path = directory / REFERENCE_DATASET_FILE
    manifest = _read_json_object(manifest_path) if manifest_path.is_file() else dict(entry)
    if manifest_path.is_file() and manifest.get("schema_version") != 1:
        raise ValueError(f"schema_version của {manifest_path} phải bằng 1.")
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


def load_reference_registry(root: Path = REFERENCE_ROOT) -> tuple[tuple[ReferenceDataset, ...], str | None]:
    path = root / REFERENCE_REGISTRY_FILE
    document = _read_json_object(path)
    if document.get("schema_version") != 1:
        raise ValueError(f"schema_version của {path} phải bằng 1.")
    entries = document.get("sets")
    if not isinstance(entries, list) or not all(isinstance(row, dict) for row in entries):
        raise ValueError(f"{path} phải khai báo danh sách bộ tham chiếu.")
    datasets = tuple(_parse_dataset(entry, root) for entry in entries)
    ids = [dataset.set_id for dataset in datasets]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path} chứa set_id trùng nhau.")
    raw_default = document.get("default_set")
    default = str(raw_default).strip().lower() if raw_default is not None else None
    if default == "":
        default = None
    if default is not None and default not in {dataset.set_id for dataset in datasets if dataset.enabled}:
        raise ValueError(f"default_set {default!r} không tồn tại hoặc đã bị tắt.")
    return datasets, default


def load_reference_registry_tolerant(root: Path = REFERENCE_ROOT) -> ReferenceRegistry:
    """Load registered sets and discover additional manifests in direct children.

    Explicit registry entries always win over auto-discovered directories, including
    when an explicit entry is disabled or broken. This keeps refresh deterministic
    and prevents discovery from silently replacing an operator-selected source.
    """
    path = root / REFERENCE_REGISTRY_FILE
    document = _read_json_object(path)
    if document.get("schema_version") != 1:
        raise ValueError(f"schema_version của {path} phải bằng 1.")
    entries = document.get("sets")
    if not isinstance(entries, list) or not all(isinstance(row, dict) for row in entries):
        raise ValueError(f"{path} phải khai báo danh sách bộ tham chiếu.")

    datasets: list[ReferenceDataset] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    reserved_ids: set[str] = set()
    registered_directories: set[Path] = set()
    registered_count = 0
    for index, entry in enumerate(entries, start=1):
        entry_id = str(entry.get("id") or entry.get("set_id") or f"mục {index}").strip().lower()
        if entry_id:
            reserved_ids.add(entry_id)
        try:
            registered_directories.add(
                _safe_child(root, str(entry.get("path") or entry_id), field="path").resolve()
            )
        except ValueError:
            pass
        try:
            dataset = _parse_dataset(entry, root)
            if dataset.set_id in seen_ids:
                raise ValueError(f"{path} chứa set_id trùng nhau: {dataset.set_id!r}.")
            seen_ids.add(dataset.set_id)
            if dataset.enabled:
                datasets.append(dataset)
                registered_count += 1
        except (OSError, ValueError) as exc:
            warnings.append(f"Bộ {entry_id!r} không khả dụng: {exc}")

    discovered_count = 0
    duplicate_count = 0
    ignored_directory_count = 0
    try:
        child_directories = sorted(
            (child for child in root.iterdir() if child.is_dir()),
            key=lambda child: child.name.casefold(),
        )
    except OSError as exc:
        raise ValueError(f"Không thể quét thư mục dữ liệu tham chiếu {root}: {exc}") from exc

    for directory in child_directories:
        if directory.resolve() in registered_directories:
            continue
        if directory.resolve() == LEGACY_REFERENCE_DIRECTORY.resolve():
            # The fixed v4.1.6 compatibility fixtures are validated separately
            # and must not appear as a user-selectable auto-discovered dataset.
            continue
        manifest_path = directory / REFERENCE_DATASET_FILE
        if not manifest_path.is_file():
            project_manifest = directory / "manifest.json"
            if not project_manifest.is_file():
                ignored_directory_count += 1
                continue
            try:
                dataset, inspection = _discover_project_dataset(directory)
                if dataset.set_id in reserved_ids or dataset.set_id in seen_ids:
                    duplicate_count += 1
                    # Registry precedence resolves this deterministically. Keep the
                    # duplicate counter for diagnostics without presenting a warning.
                    continue
                seen_ids.add(dataset.set_id)
                datasets.append(dataset)
                discovered_count += 1
                if inspection.get("status") != "PASS":
                    warnings.append(
                        f"Project tự phát hiện {directory} được đưa vào danh sách nhưng chưa đạt kiểm tra; "
                        "xem chi tiết trong tab Dữ liệu tham chiếu."
                    )
            except (OSError, ValueError) as exc:
                warnings.append(f"Project tự phát hiện tại {directory} không khả dụng: {exc}")
            continue
        try:
            manifest = _read_json_object(manifest_path)
            discovered_id = str(manifest.get("set_id") or "").strip().lower()
            dataset = _parse_dataset(
                {
                    "id": discovered_id,
                    "path": directory.name,
                    "enabled": manifest.get("enabled", True),
                },
                root,
            )
            if dataset.set_id in reserved_ids or dataset.set_id in seen_ids:
                duplicate_count += 1
                # Registry precedence resolves this deterministically. Keep the
                # duplicate counter for diagnostics without presenting a warning.
                continue
            seen_ids.add(dataset.set_id)
            if dataset.enabled:
                datasets.append(dataset)
                discovered_count += 1
        except (OSError, ValueError) as exc:
            warnings.append(f"Bộ tự phát hiện tại {directory} không khả dụng: {exc}")

    requested_default = str(document.get("default_set") or "").strip().lower()
    available_ids = {dataset.set_id for dataset in datasets}
    default = requested_default if requested_default in available_ids else None
    if requested_default and default is None:
        warnings.append(
            f"Bộ mặc định {requested_default!r} không khả dụng; hãy chọn một bộ khác hoặc không dùng bộ mẫu."
        )
    return ReferenceRegistry(
        tuple(datasets), default, tuple(warnings), registered_count,
        discovered_count, duplicate_count, ignored_directory_count,
    )


def discover_reference_datasets(root: Path = REFERENCE_ROOT) -> tuple[ReferenceDataset, ...]:
    return load_reference_registry_tolerant(root).datasets


def get_reference_dataset(set_id: str | None = None, *, root: Path = REFERENCE_ROOT) -> ReferenceDataset:
    registry = load_reference_registry_tolerant(root)
    datasets, default = registry.datasets, registry.default_set
    requested_value = set_id or os.environ.get(REFERENCE_SET_ENV) or default
    if requested_value is None:
        available = ", ".join(dataset.set_id for dataset in datasets if dataset.enabled)
        raise ValueError(
            "Chưa chọn bộ tham chiếu và registry không cấu hình default_set. "
            f"Các bộ khả dụng: {available}."
        )
    requested = requested_value.strip().lower()
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
