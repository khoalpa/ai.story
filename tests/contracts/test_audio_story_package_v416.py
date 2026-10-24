from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio.gui.helpers import (
    convert_canonical_to_plain_text,
    convert_canonical_to_raw_text,
)
from audio.story_package_v416 import (
    load_package_bytes,
    parse_story_text,
    validate_story,
)


def test_v416_story_converts_to_render_and_raw_scripts(sample_story_text: str) -> None:
    source = sample_story_text
    plain = convert_canonical_to_plain_text(source)
    raw = convert_canonical_to_raw_text(source)

    assert "# SOURCE_PROMPT: 4.1.6" in plain
    assert "# SOURCE_SCHEMA: 4.1.3" in plain
    assert "// LỜI CHÀO" in plain
    assert "[RATE=+0%]" in plain
    assert parse_story_text(source)["script"][0]["text"] == raw.splitlines()[0]


def test_v416_story_validation_rejects_old_authoring_shape() -> None:
    old = {
        "meta": {"title": "old"},
        "outline": {"greeting": "old"},
        "script": [{"zone": "LỜI CHÀO", "environment": "none", "voice": "NARRATOR", "text": "old"}],
    }
    errors = validate_story(old)
    assert any("gói cũ không được hỗ trợ" in error for error in errors)
    with pytest.raises(ValueError, match="v4.1.6"):
        parse_story_text(json.dumps(old, ensure_ascii=False))


@pytest.mark.parametrize("name,stage", [
    ("story_stage1.zip", "STAGE1"), ("story_stage2.zip", "STAGE2"),
    ("story.zip", "STAGE3"), ("story_video_prompts.zip", "STAGE4"),
])
def test_audio_opens_verified_v416_sample_packages(name: str, stage: str, sample_archives_dir: Path) -> None:
    text, inspection = load_package_bytes((sample_archives_dir / name).read_bytes())
    assert parse_story_text(text)["schema_version"] == "4.1.3"
    assert inspection["status"] == "PASS"
    assert inspection["compatibility"] == "NATIVE_CURRENT"
    assert inspection["stage"] == stage


def test_audio_rejects_zip_without_v416_manifest(tmp_path: Path) -> None:
    import zipfile
    package = tmp_path / "old.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("story.json", '{"schema_version":"3.16"}')
    with pytest.raises(ValueError, match="v4.1.6"):
        load_package_bytes(package.read_bytes())
