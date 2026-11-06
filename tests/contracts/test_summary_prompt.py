from __future__ import annotations

from pathlib import Path

import pytest

from studio.prompt_contract import PROJECT_ROOT
from studio.prompt_library import (
    discover_summary_prompt_files,
    load_summary_prompt,
    search_prompt,
)
from studio.summary_prompt_contract import (
    CURRENT_SUMMARY_PROMPT_FILENAME,
    SUPPORTED_SUMMARY_PROMPT_FILENAMES,
    discover_summary_prompts,
    load_summary_prompt_contract,
)

SUMMARY_PROMPT = PROJECT_ROOT / "prompts" / CURRENT_SUMMARY_PROMPT_FILENAME


def test_summary_prompt_contract_is_self_consistent() -> None:
    contract = load_summary_prompt_contract(SUMMARY_PROMPT)

    assert contract.version == (1, 4, 0)
    assert contract.summary_schema_version == "1.1.0"
    assert contract.story_projection_schema_version == "4.1.3"
    assert contract.plain_script_format_version == "1.1.0"
    assert contract.default_image_mode == "SCENE"
    assert len(contract.sha256) == 64


def test_summary_prompt_library_parses_and_searches() -> None:
    document = load_summary_prompt(SUMMARY_PROMPT)

    assert document.modules[0].name == "0."
    assert any(module.name == "8." for module in document.modules)
    assert search_prompt(document, "summary.json canonical")


def test_summary_discovery_is_separate_from_story_prompts(tmp_path: Path) -> None:
    for name in (*SUPPORTED_SUMMARY_PROMPT_FILENAMES, "summary_prompt_v0.9.0.txt", "notes.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")

    expected = [tmp_path / name for name in SUPPORTED_SUMMARY_PROMPT_FILENAMES]
    assert discover_summary_prompts(tmp_path) == expected
    assert discover_summary_prompt_files(tmp_path) == expected


def test_summary_loader_rejects_renamed_or_incomplete_prompt(tmp_path: Path) -> None:
    renamed = tmp_path / "summary_prompt_v0.9.0.txt"
    renamed.write_text(SUMMARY_PROMPT.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="Chỉ hỗ trợ"):
        load_summary_prompt_contract(renamed)

    incomplete = tmp_path / CURRENT_SUMMARY_PROMPT_FILENAME
    incomplete.write_text(
        "CHATGPT SUMMARY & ANALYSIS PACKAGE — v1.4.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="thiếu contract"):
        load_summary_prompt_contract(incomplete)


def test_summary_prompt_uses_namespaced_artifacts_and_explicit_projections() -> None:
    text = SUMMARY_PROMPT.read_text(encoding="utf-8")

    required = (
        "summary_narration.txt",
        "summary_visual_plan.json",
        "summary_image_prompts.json",
        "summary_render_plan.json",
        "summary_render_log.json",
        "summary_media_review.json",
        "summary_video_prompts.json",
        "summary_validation_report.json",
        "summary_manifest.json",
        "AUDIO_STORY_PLAIN v1.1.0",
        'story.json` schema 4.1.3',
        "image_mode=SCENE",
        "`landscape/` và `portrait/`",
    )
    assert all(literal in text for literal in required)


def test_summary_prompt_is_in_distribution_configuration() -> None:
    root_pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    studio_pyproject = (PROJECT_ROOT / "packages" / "studio" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert CURRENT_SUMMARY_PROMPT_FILENAME in root_pyproject
    assert CURRENT_SUMMARY_PROMPT_FILENAME in studio_pyproject
    assert "summary_prompt_v*.txt" in manifest
