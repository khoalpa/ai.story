from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.reference_samples import (
    REFERENCE_SET_ENV,
    discover_reference_datasets,
    get_reference_dataset,
    load_reference_registry,
    load_reference_registry_tolerant,
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
