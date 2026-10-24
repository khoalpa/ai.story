from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Callable

import pytest

from studio.reference_samples import (
    REFERENCE_CHECKSUM_FILE,
    REFERENCE_PACKAGE_DIRECTORY,
    load_reference_package,
    reference_checksums,
)


def test_missing_sample_is_an_actionable_failure(tmp_path: Path) -> None:
    shutil.copyfile(REFERENCE_PACKAGE_DIRECTORY / REFERENCE_CHECKSUM_FILE, tmp_path / REFERENCE_CHECKSUM_FILE)
    with pytest.raises(ValueError, match="story_stage1.zip.*samples"):
        load_reference_package("story_stage1.zip", tmp_path)


def test_changed_archive_bytes_are_rejected_before_schema_validation(tmp_path: Path) -> None:
    shutil.copyfile(REFERENCE_PACKAGE_DIRECTORY / REFERENCE_CHECKSUM_FILE, tmp_path / REFERENCE_CHECKSUM_FILE)
    (tmp_path / "story_stage1.zip").write_bytes((REFERENCE_PACKAGE_DIRECTORY / "story_stage1.zip").read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Checksum ZIP mẫu không khớp"):
        load_reference_package("story_stage1.zip", tmp_path)


def test_matching_checksum_does_not_bypass_stage_validation(tmp_path: Path) -> None:
    raw = (REFERENCE_PACKAGE_DIRECTORY / "story_stage1.zip").read_bytes()
    hashes = reference_checksums()
    hashes["story_stage2.zip"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / REFERENCE_CHECKSUM_FILE).write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="utf-8")
    (tmp_path / "story_stage2.zip").write_bytes(raw)
    with pytest.raises(ValueError, match="STAGE2"):
        load_reference_package("story_stage2.zip", tmp_path)


def test_checksum_file_must_not_contain_duplicate_entries(tmp_path: Path) -> None:
    raw = (REFERENCE_PACKAGE_DIRECTORY / REFERENCE_CHECKSUM_FILE).read_text(encoding="utf-8")
    (tmp_path / REFERENCE_CHECKSUM_FILE).write_text(raw + raw.splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="trùng tên"):
        reference_checksums(tmp_path)


def test_extracted_projects_are_isolated_and_leave_reference_bytes_untouched(
    extract_sample_package: Callable[[str], Path], tmp_path: Path,
) -> None:
    first = extract_sample_package("story_stage1.zip")
    original = (first / "story.json").read_bytes()
    (first / "story.json").write_bytes(b"edited by a test")
    second = extract_sample_package("story_stage1.zip")
    assert first != second
    assert first.is_relative_to(tmp_path) and second.is_relative_to(tmp_path)
    assert (second / "story.json").read_bytes() == original
    assert load_reference_package("story_stage1.zip")[0]["story.json"] == original


def test_reference_story_tab_works_without_output_directory(monkeypatch, tmp_path: Path) -> None:
    from streamlit.testing.v1 import AppTest

    from studio import prompt_library

    def refuse_working_output(*_args, **_kwargs):
        raise AssertionError("Reference story must not read a working output directory")

    monkeypatch.setattr(prompt_library, "inspect_directory", refuse_working_output)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_string("from studio.prompt_library import _render_reference_story\n_render_reference_story()", default_timeout=30)
    app.run()
    assert not app.exception
    assert not app.error
    assert any(metric.value == "STAGE4" for metric in app.metric)
    assert not (tmp_path / "output").exists()
