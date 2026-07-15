from __future__ import annotations

import json

from story.gui.input_bundle import scan_input_bundle


def test_scan_input_bundle_detects_story_and_prompt_files(tmp_path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "story.json").write_text(json.dumps({"meta": {}, "outline": {}, "script": []}), encoding="utf-8")
    (input_dir / "cover_prompt.json").write_text(json.dumps({"prompt": "cover"}), encoding="utf-8")
    (input_dir / "opening_prompt.json").write_text(json.dumps({"prompt": "opening"}), encoding="utf-8")

    bundle = scan_input_bundle(input_dir)

    assert bundle.has_story is True
    assert bundle.has_prompts is True
    assert [path.name for path in bundle.prompt_files] == ["cover_prompt.json", "opening_prompt.json"]
    assert bundle.summary()["prompt_count"] == 2


def test_scan_input_bundle_reports_invalid_prompt(tmp_path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "cover_prompt.json").write_text(json.dumps({"title": "missing prompt"}), encoding="utf-8")

    bundle = scan_input_bundle(input_dir)

    assert bundle.has_prompts is False
    assert "missing prompt" in bundle.prompt_error
