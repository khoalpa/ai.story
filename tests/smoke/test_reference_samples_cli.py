from __future__ import annotations

import json
from pathlib import Path

from scripts import check_reference_samples as checker
from studio.reference_samples import load_reference_registry


def test_registered_empty_registry_still_checks_tracking(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["check_reference_samples.py", "--registered", "--require-tracked"])
    monkeypatch.setattr(checker, "load_reference_registry", lambda: ((), None))
    tracked: list[set[str]] = []
    monkeypatch.setattr(checker, "check_tracked_paths", tracked.append)

    assert checker.main() == 0
    assert tracked == [{"samples/registry.json"}]
    assert "No enabled reference datasets" in capsys.readouterr().out


def test_registered_invalid_registry_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "registry.json").write_text(json.dumps({"schema_version": 99, "sets": []}))
    monkeypatch.setattr("sys.argv", ["check_reference_samples.py", "--registered"])
    monkeypatch.setattr(checker, "load_reference_registry", lambda: load_reference_registry(tmp_path))

    assert checker.main() == 1
    assert "schema_version" in capsys.readouterr().err


def test_registered_missing_package_still_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    dataset = checker.ReferenceDataset("test", "Test", tmp_path, "4.1.6", {"STAGE1": "story_stage1.zip"})
    monkeypatch.setattr("sys.argv", ["check_reference_samples.py", "--registered"])
    monkeypatch.setattr(checker, "load_reference_registry", lambda: ((dataset,), None))

    assert checker.main() == 1
    assert "FAIL test" in capsys.readouterr().out
