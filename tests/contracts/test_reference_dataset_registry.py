from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.reference_samples import (
    REFERENCE_SET_ENV,
    delete_reference_sidecar,
    discover_reference_datasets,
    get_reference_dataset,
    load_reference_registry,
    load_reference_registry_tolerant,
    suggest_reference_metadata,
    write_reference_sidecar,
)


def _write_set(root: Path, set_id: str, *, title: str | None = None) -> None:
    directory = root / set_id
    directory.mkdir()
    (directory / "reference-set.json").write_text(
        json.dumps({
            "schema_version": 1,
            "set_id": set_id,
            "title": title or set_id,
            "prompt_version": "4.1.6",
            "project_directory": ".",
        }),
        encoding="utf-8",
    )


def _write_registry(root: Path, default: str = "first") -> None:
    (root / "registry.json").write_text(
        json.dumps({
            "schema_version": 1,
            "default_set": default,
            "sets": [
                {"id": "first", "path": "first", "enabled": True},
                {"id": "second", "path": "second", "enabled": True},
            ],
        }),
        encoding="utf-8",
    )


def test_registry_discovers_enabled_sets_and_default(tmp_path: Path) -> None:
    _write_set(tmp_path, "first", title="Bộ thứ nhất")
    _write_set(tmp_path, "second")
    _write_registry(tmp_path)

    assert [row.set_id for row in discover_reference_datasets(tmp_path)] == ["first", "second"]
    assert get_reference_dataset(root=tmp_path).title == "Bộ thứ nhất"


def test_registry_allows_no_default_set(tmp_path: Path) -> None:
    _write_set(tmp_path, "first")
    _write_set(tmp_path, "second")
    _write_registry(tmp_path)
    document = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    document["default_set"] = None
    (tmp_path / "registry.json").write_text(json.dumps(document), encoding="utf-8")

    datasets, default = load_reference_registry(tmp_path)

    assert [dataset.set_id for dataset in datasets] == ["first", "second"]
    assert default is None
    assert load_reference_registry_tolerant(tmp_path).default_set is None
    with pytest.raises(ValueError, match="Chưa chọn bộ tham chiếu"):
        get_reference_dataset(root=tmp_path)


def test_empty_registry_uses_auto_discovery_without_choosing_default(tmp_path: Path) -> None:
    _write_set(tmp_path, "first")
    (tmp_path / "registry.json").write_text(
        json.dumps({"schema_version": 1, "default_set": None, "sets": []}),
        encoding="utf-8",
    )

    registry = load_reference_registry_tolerant(tmp_path)

    assert [dataset.set_id for dataset in registry.datasets] == ["first"]
    assert registry.default_set is None
    assert get_reference_dataset("first", root=tmp_path).set_id == "first"


def test_explicit_selection_precedes_environment(monkeypatch, tmp_path: Path) -> None:
    _write_set(tmp_path, "first")
    _write_set(tmp_path, "second")
    _write_registry(tmp_path)
    monkeypatch.setenv(REFERENCE_SET_ENV, "second")

    assert get_reference_dataset(root=tmp_path).set_id == "second"
    assert get_reference_dataset("first", root=tmp_path).set_id == "first"


def test_registry_rejects_paths_outside_samples(tmp_path: Path) -> None:
    (tmp_path / "registry.json").write_text(
        json.dumps({
            "schema_version": 1,
            "default_set": "escape",
            "sets": [{"id": "escape", "path": "../escape", "enabled": True}],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="nằm ngoài"):
        load_reference_registry(tmp_path)


def test_registry_rejects_duplicate_ids(tmp_path: Path) -> None:
    _write_set(tmp_path, "first")
    (tmp_path / "registry.json").write_text(
        json.dumps({
            "schema_version": 1,
            "default_set": "first",
            "sets": [
                {"id": "first", "path": "first"},
                {"id": "first", "path": "first"},
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="trùng"):
        load_reference_registry(tmp_path)


def test_tolerant_registry_keeps_valid_sets_and_reports_broken_default(tmp_path: Path) -> None:
    _write_set(tmp_path, "second")
    (tmp_path / "registry.json").write_text(
        json.dumps({
            "schema_version": 1,
            "default_set": "missing",
            "sets": [
                {"id": "missing", "path": "does-not-exist"},
                {"id": "second", "path": "second"},
            ],
        }),
        encoding="utf-8",
    )

    registry = load_reference_registry_tolerant(tmp_path)

    assert [dataset.set_id for dataset in registry.datasets] == ["second"]
    assert registry.default_set is None
    assert any("Không tìm thấy thư mục" in warning for warning in registry.warnings)
    assert any("Bộ mặc định" in warning for warning in registry.warnings)


def test_tolerant_registry_auto_discovers_unregistered_manifest(tmp_path: Path) -> None:
    _write_set(tmp_path, "first")
    _write_set(tmp_path, "second")
    _write_set(tmp_path, "third", title="Bộ tự phát hiện")
    _write_registry(tmp_path)
    (tmp_path / "notes").mkdir()

    registry = load_reference_registry_tolerant(tmp_path)

    assert [dataset.set_id for dataset in registry.datasets] == ["first", "second", "third"]
    assert registry.registered_count == 2
    assert registry.discovered_count == 1
    assert registry.duplicate_count == 0
    assert registry.ignored_directory_count == 1


def test_registered_dataset_wins_over_auto_discovered_duplicate(tmp_path: Path) -> None:
    _write_set(tmp_path, "first", title="Bản đăng ký")
    _write_set(tmp_path, "second")
    _write_registry(tmp_path)
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    (duplicate / "reference-set.json").write_text(
        json.dumps({
            "schema_version": 1,
            "set_id": "first",
            "title": "Bản tự phát hiện",
            "prompt_version": "4.1.6",
            "project_directory": ".",
        }),
        encoding="utf-8",
    )

    registry = load_reference_registry_tolerant(tmp_path)

    assert next(dataset for dataset in registry.datasets if dataset.set_id == "first").title == "Bản đăng ký"
    assert registry.duplicate_count == 1
    assert not any("Bỏ qua bộ tự phát hiện" in warning for warning in registry.warnings)


def test_project_manifest_is_discovered_without_reference_sidecar(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "registry.json").write_text(
        json.dumps({"schema_version": 1, "default_set": None, "sets": []}),
        encoding="utf-8",
    )
    project = tmp_path / "[DDKA-0001] Hồ sơ số không - Tập 5 - Hàng đợi thứ hai"
    project.mkdir()
    (project / "manifest.json").write_text(
        json.dumps({"schema_version": "5.0.0", "prompt_version": "5.2.2", "files": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "studio.reference_samples.inspect_directory",
        lambda _path: {"status": "PASS", "compatibility": "NATIVE_CURRENT"},
    )

    registry = load_reference_registry_tolerant(tmp_path)

    assert [dataset.set_id for dataset in registry.datasets] == ["ddka-0005"]
    assert registry.datasets[0].project_directory == "."
    assert registry.datasets[0].prompt_version == "5.2.2"
    assert registry.discovered_count == 1


def test_failing_canonical_project_remains_visible_with_warning(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "registry.json").write_text(
        json.dumps({"schema_version": 1, "default_set": None, "sets": []}),
        encoding="utf-8",
    )
    project = tmp_path / "[DKTT-0005] Truyện cần sửa"
    project.mkdir()
    (project / "manifest.json").write_text(
        json.dumps({"schema_version": "5.0.0", "prompt_version": "5.2.2", "files": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "studio.reference_samples.inspect_directory",
        lambda _path: {"status": "FAIL", "compatibility": "NATIVE_CURRENT"},
    )

    registry = load_reference_registry_tolerant(tmp_path)

    assert [dataset.set_id for dataset in registry.datasets] == ["dktt-0005"]
    assert any("chưa đạt kiểm tra" in warning for warning in registry.warnings)


def test_sidecar_lifecycle_keeps_canonical_manifest_untouched(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "registry.json").write_text(
        json.dumps({"schema_version": 1, "default_set": None, "sets": []}),
        encoding="utf-8",
    )
    project = tmp_path / "[DDKA-0001] Hồ sơ số không - Tập 5 - Hàng đợi thứ hai"
    project.mkdir()
    manifest = {"schema_version": "5.0.0", "prompt_version": "5.2.2", "files": []}
    manifest_path = project / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    original_manifest = manifest_path.read_bytes()
    monkeypatch.setattr(
        "studio.reference_samples.inspect_directory",
        lambda _path: {"status": "PASS", "compatibility": "NATIVE_CURRENT"},
    )

    metadata = suggest_reference_metadata(project)
    path = write_reference_sidecar(project, metadata, root=tmp_path)

    assert path.name == "reference-set.json"
    assert json.loads(path.read_text(encoding="utf-8"))["set_id"] == "ddka-0005"
    assert manifest_path.read_bytes() == original_manifest
    with pytest.raises(ValueError, match="đã tồn tại"):
        write_reference_sidecar(project, metadata, root=tmp_path)

    delete_reference_sidecar(project, root=tmp_path)
    assert not path.exists()
    assert manifest_path.read_bytes() == original_manifest


def test_sidecar_rejects_set_id_used_by_another_project(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "registry.json").write_text(
        json.dumps({"schema_version": 1, "default_set": None, "sets": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "studio.reference_samples.inspect_directory",
        lambda _path: {"status": "PASS", "compatibility": "NATIVE_CURRENT"},
    )
    first = tmp_path / "[DKTT-0001] Truyện thứ nhất"
    second = tmp_path / "[DKTT-0002] Truyện thứ hai"
    for project in (first, second):
        project.mkdir()
        (project / "manifest.json").write_text(
            json.dumps({"prompt_version": "5.2.2", "files": []}), encoding="utf-8"
        )

    conflicting = suggest_reference_metadata(second)
    conflicting["set_id"] = "dktt-0001"

    with pytest.raises(ValueError, match="đã được dùng"):
        write_reference_sidecar(second, conflicting, root=tmp_path)
