import copy
import json
from pathlib import Path

import pytest

from studio.prompt_contract import PROJECT_ROOT
from studio.story_catalog import (
    DEFAULT_CATALOG_ROOT,
    catalog_bytes,
    scan_story_catalog,
    validate_story_catalog,
    write_story_catalog,
)
from tests.package_fixtures import synthetic_story


def _sample_story() -> dict:
    return synthetic_story()


def _write_story(directory: Path, story: dict) -> bytes:
    directory.mkdir(parents=True)
    raw = (json.dumps(story, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (directory / "story.json").write_bytes(raw)
    return raw


def test_default_catalog_root_is_samples() -> None:
    assert DEFAULT_CATALOG_ROOT == PROJECT_ROOT / "samples"


def test_scan_groups_exact_story_variants_and_omits_absolute_paths(tmp_path: Path) -> None:
    story = _sample_story()
    _write_story(tmp_path / "package-a", story)
    _write_story(tmp_path / "package-b", story)

    catalog = scan_story_catalog(tmp_path, generated_at="2026-11-04T00:00:00Z")

    assert catalog["summary"] == {
        "story_count": 1, "package_variant_count": 2,
        "invalid_source_count": 0, "duplicate_group_count": 0,
    }
    variants = catalog["stories"][0]["package_variants"]
    assert {row["path"] for row in variants} == {"package-a", "package-b"}
    assert all("absolute_path" not in row for row in variants)


def test_scan_detects_same_normalized_title_and_invalid_source(tmp_path: Path) -> None:
    first = _sample_story()
    second = copy.deepcopy(first)
    second["meta"]["title"] = f"  {first['meta']['title'].upper()}!  "
    second["script"][0]["text"] += " Một chi tiết khác."
    _write_story(tmp_path / "first", first)
    _write_story(tmp_path / "second", second)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "story.json").write_text("{}", encoding="utf-8")

    catalog = scan_story_catalog(tmp_path)

    assert catalog["summary"]["story_count"] == 2
    assert catalog["summary"]["invalid_source_count"] == 1
    assert any(group["kind"] == "SAME_NORMALIZED_TITLE" for group in catalog["duplicate_groups"])
    assert catalog["invalid_sources"][0]["path"] == "broken"


def test_catalog_roundtrip_and_safe_relative_paths(tmp_path: Path) -> None:
    _write_story(tmp_path / "package", _sample_story())
    catalog = scan_story_catalog(tmp_path)
    destination = write_story_catalog(catalog, tmp_path / "story_catalog.json")
    loaded = json.loads(destination.read_text(encoding="utf-8"))
    assert catalog_bytes(loaded).endswith(b"\n")
    loaded["stories"][0]["package_variants"][0]["path"] = "../escape"
    with pytest.raises(ValueError, match="tương đối an toàn"):
        validate_story_catalog(loaded)


def test_catalog_rejects_inconsistent_summary(tmp_path: Path) -> None:
    _write_story(tmp_path / "package", _sample_story())
    catalog = scan_story_catalog(tmp_path)
    catalog["summary"]["story_count"] += 1
    with pytest.raises(ValueError, match="summary không khớp"):
        validate_story_catalog(catalog)


def test_prompt_v522_r3_is_full_self_contained_three_stage_contract() -> None:
    prompt = (PROJECT_ROOT / "prompts" / "ChatGPT_prompt_v5.2.2.txt").read_text(encoding="utf-8")
    assert len(prompt.splitlines()) >= 900
    required_topics = (
        "KIỂM TRA KHẢ NĂNG THỰC TẾ", "BA PROFILE VÀ AN TOÀN NỘI DUNG",
        "STORY_NOVELTY", "image_prompts.json root đóng",
        "VIDEO_PROMPTS.JSON — ARTIFACT BẮT BUỘC STAGE 1",
        "SERIES, MANH MỐI VÀ NGHĨA VỤ KẾT THÚC",
        "CHI TIẾT HÌNH ẢNH, PILOT VÀ KIỂM TOÀN BỘ",
        "CHECKPOINT, PHỤ THUỘC VÀ BẰNG CHỨNG THỰC TẾ",
        "CHARACTER IMAGE PACK", "story_stage1.zip", "story_stage2.zip",
    )
    assert all(topic in prompt for topic in required_topics)
    assert "image_prompts.json\n  video_prompts.json" in prompt
    assert 'prompt_version="5.2.2"; stage integer 1..3' in prompt
    assert "Không tồn tại Stage 4/5 trong writer v5" in prompt
    assert "CHÍNH SÁCH PHÁT HÀNH PROMPT RÚT GỌN — REVISION r3" in prompt
