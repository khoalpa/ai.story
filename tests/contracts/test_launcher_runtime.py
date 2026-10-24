from __future__ import annotations

import importlib.metadata
import sys

import pytest

from scripts import check_runtime


@pytest.mark.parametrize("version,expected", [("3.9.9", False), ("3.10.0", True), ("3.12.9", True), ("3.13.0", False)])
def test_launcher_respects_both_python_bounds(version, expected):
    python_requirement, _ = check_runtime.runtime_requirements()
    assert check_runtime.meets_requirement(version, python_requirement) is expected


@pytest.mark.parametrize("version", [None, "1.48.0", "2.0.0", "1.49.0rc1"])
def test_launcher_blocks_missing_or_unsupported_streamlit(monkeypatch, capsys, version):
    monkeypatch.setattr(sys, "version_info", (3, 12, 1))

    def installed(_name):
        if version is None:
            raise importlib.metadata.PackageNotFoundError("streamlit")
        return version

    monkeypatch.setattr(importlib.metadata, "version", installed)
    assert check_runtime.main() == 1
    output = capsys.readouterr().out
    assert "pip install -r" in output
    assert sys.executable in output


def test_launcher_accepts_supported_runtime(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 12, 1))
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "1.49.0")
    assert check_runtime.main() == 0
