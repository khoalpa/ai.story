from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from studio.artifact_validation import strict_json_bytes, validate_archive
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
