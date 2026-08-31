from __future__ import annotations

from pathlib import Path

from studio.prompt_contract import (
    canonical_prompt_path,
    discover_canonical_prompts,
    load_prompt_contract,
)
from studio.story_environments import CANONICAL_STORY_ENVIRONMENTS
from studio.story_images import EXPECTED_IMAGE_STEMS


def test_latest_prompt_is_selected_by_semantic_version(tmp_path: Path) -> None:
    for name in (
        "ChatGPT_prompt_v3.9.99.txt",
        "ChatGPT_prompt_v3.11.12.txt",
        "ChatGPT_prompt_v3.12.0.txt",
    ):
        (tmp_path / name).write_text("placeholder", encoding="utf-8")
    assert canonical_prompt_path(tmp_path).name == "ChatGPT_prompt_v3.12.0.txt"
    assert [path.name for path in discover_canonical_prompts(tmp_path)][0] == "ChatGPT_prompt_v3.12.0.txt"


def test_runtime_projection_matches_latest_prompt() -> None:
    contract = load_prompt_contract()
    assert tuple(name.removesuffix(".png") for name in contract.image_basenames) == EXPECTED_IMAGE_STEMS
    assert contract.environment_whitelist == CANONICAL_STORY_ENVIRONMENTS
    assert contract.landscape_size == (3840, 2160)
    assert contract.portrait_size == (1080, 1920)
    assert contract.story_validation_schema_version == "2.3"
    assert contract.package_quality_schema_version == "2.0"
    assert contract.series_anchor_schema_version == "3.2.0"
