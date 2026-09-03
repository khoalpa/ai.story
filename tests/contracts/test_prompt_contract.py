from __future__ import annotations

from pathlib import Path

import pytest

from studio.prompt_contract import (
    canonical_prompt_path,
    discover_canonical_prompts,
    load_prompt_contract,
)
from studio.story_environments import CANONICAL_STORY_ENVIRONMENTS
from studio.story_images import EXPECTED_IMAGE_STEMS


def test_current_registries_are_resolved_and_immutable() -> None:
    contract = load_prompt_contract()
    assert contract.current_public_schema_registry["video_prompt"] == "1.1"
    assert contract.current_enum_registry["video_audio_mode"] == (
        "AMBIENCE_ONLY", "NATIVE_DIALOGUE", "SILENT",
    )
    with pytest.raises(TypeError):
        contract.current_public_schema_registry["video_prompt"] = "changed"


def test_explicit_prompt_file_environment_takes_priority(tmp_path: Path, monkeypatch) -> None:
    selected = tmp_path / "ChatGPT_prompt_v1.2.3.txt"
    selected.write_text("prompt", encoding="utf-8")
    monkeypatch.setenv("AI_STUDIO_PROMPT_FILE", str(selected))

    assert canonical_prompt_path() == selected.resolve()


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
    assert contract.video_prompt_schema_version == "1.1"
    assert contract.video_prompt_default_config["audio_mode"] == "NATIVE_DIALOGUE"
    prompt_text = contract.path.read_text(encoding="utf-8-sig")
    assert "VIDEO-PROMPT-CANONICAL-SOURCE-01:" in prompt_text
    assert "video_prompts.flow.json" in prompt_text
    assert "LITERAL-REACHABILITY-01:" in prompt_text
    assert "VEO_VIDEO_PROMPT_SCHEMA_VERSION" not in prompt_text
    assert "VIDEO_SENTENCE_USABLE_SPAN_MAX_SECONDS = 7.950" in prompt_text
    assert "Mỗi clip có đúng 22 field" in prompt_text
    assert "voice_plan" in prompt_text
    assert "VOICE_PROJECTION_LOSS" in prompt_text
    assert "BASELINE_HISTORY_" not in prompt_text
    global_constants = prompt_text[
        prompt_text.index("GLOBAL CONSTANTS"):prompt_text.index("===== MODULE:CANONICAL_REGISTRY END =====")
    ]
    assert "STORY_LEGACY_SCHEMA_VERSIONS" not in global_constants
    legacy_overlay = prompt_text[
        prompt_text.index("===== OVERLAY:LEGACY_INPUT_COMPATIBILITY BEGIN ====="):
        prompt_text.index("===== OVERLAY:LEGACY_INPUT_COMPATIBILITY END =====")
    ]
    assert "STORY_LEGACY_SCHEMA_VERSIONS" in legacy_overlay
    assert "LEGACY_STAGE1_CHECKPOINT_NAME" in legacy_overlay
    assert "LEGACY_IMAGE_PROVENANCE_SCHEMA_BY_STAGE" in legacy_overlay
    assert "STAGE2_BACKEND_ADAPTER_SCHEMA_VERSION" not in prompt_text
    assert "STAGE2_PROVENANCE_SCHEMA_VERSION" not in prompt_text
    assert "STAGE3_PORTRAIT_PROVENANCE_SCHEMA_VERSION" not in prompt_text
    assert "STAGE2_CANONICAL_BASENAME_SET" not in prompt_text
    release_overlay = prompt_text[
        prompt_text.index("===== OVERLAY:FRAMEWORK_RELEASE_AUDIT BEGIN ====="):
        prompt_text.index("===== OVERLAY:FRAMEWORK_RELEASE_AUDIT END =====")
    ]
    assert "EXTERNAL_CONFORMANCE_BUNDLE_REQUIRED" in release_overlay
    assert "EXTERNAL_CONFORMANCE_BUNDLE_BINDING_FIELDS" in release_overlay
    assert "FIXTURE_REGISTRY_SCHEMA_VERSION" not in prompt_text
    assert "PHYSICAL_SLICE_MANIFEST_SCHEMA_VERSION" not in prompt_text
    assert "VIDEO_PROMPT_DEFAULT_CONFIG" in prompt_text
    assert "META_LEAK_LIMIT_BY_CLASS" in prompt_text
    assert "image_evidence` tuyệt đối không được serialize trực tiếp thành array" in prompt_text
    assert "literal hiển thị `16:9`/`9:16` chỉ dành" in prompt_text
    assert "CURRENT_PUBLIC_SCHEMA_REGISTRY" in prompt_text
    assert "CURRENT_ENUM_REGISTRY" in prompt_text
    assert "CURRENT_CONFIG_REGISTRY" in prompt_text
    assert "RUNTIME_DEFAULT_CONFIG" in prompt_text
    assert "IMAGE_TRANSACTION_LIMITS" in prompt_text
    assert "MANAGED_UPSCALE_LIMITS" in prompt_text
    assert "COVER_RENDER_RECORD_ORIENTATION_ENUM" not in prompt_text
    assert "VISUAL_REALIZATION_ORIENTATION_ENUM" not in prompt_text
    assert "DEFAULT_FRAMEWORK_OPERATION_MODE" not in prompt_text


def test_numbered_prompts_share_discovery_and_loading_with_library(tmp_path: Path) -> None:
    from studio.prompt_library import discover_prompt_files, load_prompt

    source = load_prompt_contract().path.read_bytes()
    names = (
        "ChatGPT_prompt_v3.9.99.txt",
        "02-ChatGPT_prompt_v3.11.14.txt",
        "01-ChatGPT_prompt_v3.12.0.txt",
    )
    for name in (*names, "draft-ChatGPT_prompt_v9.0.0.txt"):
        (tmp_path / name).write_bytes(source)
    expected = [tmp_path / name for name in reversed(names)]
    assert discover_canonical_prompts(tmp_path) == expected
    assert discover_prompt_files(tmp_path) == expected
    selected = canonical_prompt_path(tmp_path)
    assert load_prompt_contract(selected).version == (3, 12, 0)
    assert load_prompt(selected).version == (3, 12, 0)
