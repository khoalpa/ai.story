from __future__ import annotations

from studio.image_prompt_validation import validate_image_prompt_plan
from studio.story_schema import validate_story_document
from studio.summary_projection import (
    project_summary_to_image_prompts,
    project_summary_to_story,
    project_summary_to_video_prompts,
    project_summary_to_visual_plan,
)
from studio.summary_schema import validate_summary_document
from studio.video_prompt_v4 import validate_v5_plan
from studio.workflow_package import active_image_basenames, validate_visual_plan


def summary_fixture() -> dict:
    return {
        "schema_version": "1.1.0", "prompt_version": "1.4.0",
        "meta": {"title": "Bản tóm tắt kiểm thử", "output_type": "SUMMARY_ANALYSIS",
                 "source_genre": "NONFICTION", "style": "NEUTRAL_CLEAR",
                 "audience": "Người trưởng thành phổ thông", "language": "vi",
                 "target_words": 80, "target_minutes": 1, "image_mode": "SCENE",
                 "coverage": "FULL_SUMMARY", "citation_style": "MARKDOWN",
                 "scene_density_seconds": 30, "max_scenes": 20},
        "sources": [{"source_id": "src_001", "title": "Nguồn mẫu", "type": "TEXT",
                     "version": None, "authors": ["Tác giả mẫu"], "published_at": "2026",
                     "publisher": "Nhà xuất bản mẫu", "url": "https://example.test/source",
                     "accessed_at": "2026-11-06", "mime_type": "text/plain", "size_bytes": None,
                     "sha256": None, "extraction_method": "DIRECT_TEXT", "ocr_status": "NOT_APPLICABLE",
                     "scope_read": "Toàn bộ"}],
        "locators": [{"locator_id": "loc_0001", "source_id": "src_001", "kind": "TEXT_OFFSET",
                      "label": "Đoạn 1", "page": None, "section": "1", "start_char": 0,
                      "end_char": 120, "timestamp_start_ms": None, "timestamp_end_ms": None}],
        "sections": [{"section_id": "section_001", "source_id": "src_001",
                      "locator_ids": ["loc_0001"], "summary": "Nguồn trình bày một quy trình rõ ràng.",
                      "key_points": ["Xác định vấn đề", "Kiểm tra bằng chứng"], "uncertainties": []}],
        "claims": [{"claim_id": "claim_0001", "statement": "Quy trình gồm nhiều bước kiểm tra.",
                    "claim_type": "SOURCE", "source_ids": ["src_001"], "locator_ids": ["loc_0001"],
                    "confidence": "HIGH", "included_in_summary": True}],
        "claim_relations": [],
        "numeric_facts": [{"numeric_fact_id": "num_0001", "value": 8, "unit": "bước",
                           "population": "quy trình", "period": None, "locator_ids": ["loc_0001"]}],
        "glossary": [{"term": "bằng chứng", "definition": "Thông tin dùng để kiểm tra nhận định",
                      "original_term": None, "do_not_translate": False, "locator_ids": ["loc_0001"]}],
        "narration": [{"narration_id": "narration_0001", "section_id": "section_001",
                       "text": "Tài liệu bắt đầu bằng việc xác định vấn đề, sau đó thu thập bằng chứng, kiểm tra giả định, so sánh lựa chọn, đánh giá rủi ro, chọn phương án, thực hiện và cuối cùng xem lại kết quả.",
                       "claim_ids": ["claim_0001"]}],
        "limitations": [],
    }


def test_summary_projection_passes_all_current_target_validators() -> None:
    summary = summary_fixture()
    assert validate_summary_document(summary) == []

    story = project_summary_to_story(summary)
    assert validate_story_document(story) == []

    visual = project_summary_to_visual_plan(summary, story)
    assert validate_visual_plan(visual) == []
    assert active_image_basenames(visual)[:2] == ("cover.png", "greeting.png")
    assert active_image_basenames(visual)[-2:] == ("farewell.png", "outro.png")

    image_prompts = project_summary_to_image_prompts(summary, story, visual)
    import json
    story_raw = json.dumps(story, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    assert validate_image_prompt_plan(image_prompts, story, story_raw, expected_prompt_version="5.2.2") == []

    video = project_summary_to_video_prompts(summary, story)
    result = validate_v5_plan(video, members={"story.json": json.dumps(story, ensure_ascii=False).encode()})
    assert result["errors"] == []
    assert video["coverage"] == "FULL_STORY"


def test_summary_validator_rejects_broken_claim_reference() -> None:
    summary = summary_fixture()
    summary["narration"][0]["claim_ids"] = ["claim_9999"]
    assert any("claim_ids" in error for error in validate_summary_document(summary))


def test_summary_validator_accepts_specialized_output_modes() -> None:
    for mode in ("COMPARE_SOURCES", "ARGUMENT_MAP", "TIMELINE", "DATA_BRIEF", "TEACHING_SCRIPT"):
        summary = summary_fixture()
        summary["meta"]["output_type"] = mode
        assert validate_summary_document(summary) == []
