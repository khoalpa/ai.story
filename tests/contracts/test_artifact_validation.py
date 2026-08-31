from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from studio.artifact_validation import strict_json_bytes, validate_archive
from studio.prompt_audit import main as audit_main
from studio.prompt_contract import load_prompt_contract


def _png(size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size).save(output, "PNG")
    return output.getvalue()


def test_strict_json_rejects_duplicate_keys_and_nonfinite_values() -> None:
    for raw in (b'{"a":1,"a":2}', b'{"value":NaN}', b'\xef\xbb\xbf{}'):
        try:
            strict_json_bytes(raw)
        except ValueError:
            pass
        else:
            raise AssertionError(f"strict parser accepted {raw!r}")


def test_checkpoint_file_set_and_dimensions_are_deterministically_checked(tmp_path: Path) -> None:
    contract = load_prompt_contract()
    path = tmp_path / "stage2_checkpoint.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("story.json", json.dumps({"schema_version": "x"}))
        archive.writestr("visual_bible.json", "{}")
        for name in contract.image_basenames:
            archive.writestr(f"landscape/{name}", _png(contract.landscape_size))
    result = validate_archive(path, contract)
    assert result.status == "NOT_VERIFIED"
    assert result.errors == []
    assert result.checks["archive_file_set"] == "PASS"


def test_archive_rejects_wrong_portrait_dimensions_and_extra_file(tmp_path: Path) -> None:
    contract = load_prompt_contract()
    path = tmp_path / "story.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name in ("story.json", "story_validation.json", "package_quality_report.json"):
            archive.writestr(name, "{}")
        for name in contract.image_basenames:
            archive.writestr(f"landscape/{name}", _png(contract.landscape_size))
            archive.writestr(f"portrait/{name}", _png((100, 100)))
        archive.writestr("preview.jpg", b"x")
    result = validate_archive(path, contract)
    assert result.status == "FAIL"
    assert any("File thừa" in error for error in result.errors)
    assert any("portrait/cover.png: kích thước" in error for error in result.errors)


@pytest.mark.parametrize("raw", [
    b'{"value":1e999}', b'{"value":-1e999}',
    b'{"nested":[{"value":1e999}]}',
    b'{"value":Infinity}', b'{"value":-Infinity}',
])
def test_strict_json_rejects_overflow_and_infinity(raw: bytes) -> None:
    with pytest.raises(ValueError, match="không hữu hạn"):
        strict_json_bytes(raw)


def test_strict_json_preserves_finite_numbers() -> None:
    assert strict_json_bytes(b'{"values":[1.25,-1e308,1e308,42]}') == {
        "values": [1.25, -1e308, 1e308, 42],
    }


def _audit_archive(tmp_path, archive_name, *, overrides=None, prefix="", extra=None):
    contract = replace(load_prompt_contract(), landscape_size=(8, 4), portrait_size=(4, 8))
    documents = (
        ("story.json", "visual_bible.json") if archive_name == "stage2_checkpoint.zip"
        else ("story.json", "story_validation.json", "package_quality_report.json", "series_anchor.json")
    )
    entries = {name: b"{}" for name in documents}
    for name in contract.image_basenames:
        entries[f"landscape/{name}"] = _png(contract.landscape_size)
        if archive_name != "stage2_checkpoint.zip":
            entries[f"portrait/{name}"] = _png(contract.portrait_size)
    entries.update(overrides or {})
    path = tmp_path / archive_name
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in entries.items():
            archive.writestr(prefix + name, raw)
        for name, raw in (extra or {}).items():
            archive.writestr(name, raw)
    return path, contract


@pytest.mark.parametrize("archive_name,member", [
    ("stage2_checkpoint.zip", "story.json"),
    ("stage2_checkpoint.zip", "visual_bible.json"),
    ("story.zip", "story.json"),
    ("story.zip", "story_validation.json"),
    ("story.zip", "package_quality_report.json"),
    ("story.zip", "series_anchor.json"),
])
@pytest.mark.parametrize("raw", [
    b"NOT JSON", b'{"a":1,"a":2}', b'{"value":1e999}',
    b"\xef\xbb\xbf{}", b'{"value":"\xff"}', b"[]",
])
def test_archive_rejects_invalid_json(tmp_path, archive_name, member, raw) -> None:
    path, contract = _audit_archive(tmp_path, archive_name, overrides={member: raw})
    result = validate_archive(path, contract)
    assert result.status == "FAIL"
    assert result.checks["archive_json"] == "FAIL"
    assert any(member in error and "JSON" in error for error in result.errors)


@pytest.mark.parametrize("archive_name", ["stage2_checkpoint.zip", "story.zip"])
def test_archive_reads_original_member_names_after_normalization(tmp_path, archive_name) -> None:
    path, contract = _audit_archive(tmp_path, archive_name, prefix="./")
    result = validate_archive(path, contract)
    assert result.status == "NOT_VERIFIED"
    assert result.errors == []
    assert result.checks == {"archive_json": "PASS", "archive_file_set": "PASS"}


def test_archive_still_rejects_normalized_duplicate_names(tmp_path) -> None:
    path, contract = _audit_archive(
        tmp_path, "stage2_checkpoint.zip", extra={"./story.json": b"{}"},
    )
    result = validate_archive(path, contract)
    assert result.status == "FAIL"
    assert any("trùng sau chuẩn hóa" in error for error in result.errors)


def test_audit_cli_fails_for_invalid_archived_json(tmp_path, monkeypatch, capsys) -> None:
    path, contract = _audit_archive(
        tmp_path, "stage2_checkpoint.zip", overrides={"story.json": b"NOT JSON"},
    )
    monkeypatch.setattr("studio.prompt_audit.load_prompt_contract", lambda _: contract)
    assert audit_main([str(path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report[0]["status"] == "FAIL"
    assert report[0]["checks"]["archive_json"] == "FAIL"
