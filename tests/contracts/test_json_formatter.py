from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.json_formatter import (
    default_formatted_path,
    existing_picker_directory,
    format_json_file,
    save_formatted_json,
)


def test_picker_directory_uses_parent_of_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "story.json"
    source.write_text("{}", encoding="utf-8")

    assert existing_picker_directory(source) == str(tmp_path)


def test_picker_directory_uses_nearest_existing_parent(tmp_path: Path) -> None:
    missing = tmp_path / "new" / "nested" / "story.json"

    assert existing_picker_directory(missing) == str(tmp_path)


def test_formats_utf8_json_without_reordering_keys(tmp_path: Path) -> None:
    source = tmp_path / "visual_plan.json"
    source.write_text('{"z":"Tiếng Việt","a":[1,2]}', encoding="utf-8")

    result = format_json_file(source, indent=2, newline="LF")

    assert result.text.startswith('{\n  "z": "Tiếng Việt",\n  "a": [')
    assert result.text.endswith("\n")
    assert result.original_lines == 1
    assert result.formatted_lines > 1


def test_supports_crlf_and_array_root(tmp_path: Path) -> None:
    source = tmp_path / "items.json"
    source.write_text('[{"id":1}]', encoding="utf-8")

    result = format_json_file(source, indent=4, newline="CRLF")

    assert "\r\n" in result.text
    assert "\n" not in result.text.replace("\r\n", "")
    assert json.loads(result.text) == [{"id": 1}]


@pytest.mark.parametrize(
    "content, message",
    [
        ('{"x":1,"x":2}', "trùng"),
        ('{"x":NaN}', "không hữu hạn"),
    ],
)
def test_rejects_unsafe_json(tmp_path: Path, content: str, message: str) -> None:
    source = tmp_path / "unsafe.json"
    source.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        format_json_file(source)


def test_rejects_utf8_bom(tmp_path: Path) -> None:
    source = tmp_path / "bom.json"
    source.write_bytes(b"\xef\xbb\xbf{}")

    with pytest.raises(ValueError, match="BOM"):
        format_json_file(source)


def test_saves_new_file_and_verifies_content(tmp_path: Path) -> None:
    source = tmp_path / "story.json"
    source.write_text('{"b":2,"a":1}', encoding="utf-8")
    result = format_json_file(source)
    destination = default_formatted_path(source)

    target, backup = save_formatted_json(result, destination)

    assert target == destination
    assert backup is None
    assert target.read_text(encoding="utf-8") == result.text


def test_overwrite_requires_confirmation_and_creates_backup(tmp_path: Path) -> None:
    source = tmp_path / "story.json"
    original = b'{"text":"xin chao"}'
    source.write_bytes(original)
    result = format_json_file(source)

    with pytest.raises(ValueError, match="xác nhận"):
        save_formatted_json(result, source)

    target, backup = save_formatted_json(result, source, overwrite_source=True)

    assert target == source
    assert backup == source.with_suffix(".json.bak")
    assert backup.read_bytes() == original
    assert source.read_text(encoding="utf-8") == result.text


def test_repeated_overwrite_preserves_previous_backup(tmp_path: Path) -> None:
    source = tmp_path / "story.json"
    source.write_text('{"version":1}', encoding="utf-8")
    first_result = format_json_file(source)
    _, first_backup = save_formatted_json(first_result, source, overwrite_source=True)
    source.write_text('{"version":2}', encoding="utf-8")
    second_result = format_json_file(source)

    _, second_backup = save_formatted_json(second_result, source, overwrite_source=True)

    assert first_backup == source.with_suffix(".json.bak")
    assert second_backup == source.with_suffix(".json.bak.1")
    assert first_backup.read_text(encoding="utf-8") == '{"version":1}'
    assert second_backup.read_text(encoding="utf-8") == '{"version":2}'
