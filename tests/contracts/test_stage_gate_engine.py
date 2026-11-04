from __future__ import annotations

import json

import pytest

from studio.artifact_validation import validate_series_anchor_bytes
from studio.prompt_contract import load_prompt_contract
from studio.workflow_package import aggregate_package_status


def _anchor() -> dict:
    return {
        "schema_version": "4.1.3",
        "series_title": "Series thử",
        "last_completed_episode": 1,
        "characters": [{
            "character_id": "c001", "name": "Linh",
            "established_facts": ["Điều tra viên"], "known_facts": [],
        }],
        "canon_facts": [{
            "fact_id": "f001", "text": "Một sự kiện đã xảy ra", "established_episode": 1,
        }],
        "open_threads": [{"thread_id": "t001", "description": "Câu hỏi mở", "clues": []}],
        "resolved_threads": [],
        "episode_summaries": [{"episode": 1, "summary": "Tóm tắt tập một"}],
        "series_state": {
            "status": "ACTIVE",
            "next_episode_contract": {
                "episode": 2, "premise": "Tiếp tục điều tra",
                "required_thread_ids": ["t001"], "forbidden_resolutions": [],
            },
            "milestones": [],
            "clues": [{
                "clue_id": "cl001", "thread_id": "t001", "observation": "Vật chứng",
                "interpretation": None, "status": "UNRESOLVED", "introduced_episode": 1,
                "revealed_episode": None, "known_by": ["c001"], "source_script_ids": ["s0001"],
            }],
            "consequences": [], "visual_locks": [],
            "episode_designs": [{
                "episode": 1, "central_question": "Điều gì xảy ra?", "case_type": "OTHER",
                "clue_media": ["vật chứng"], "decisive_choice": "Tiếp tục",
                "ending_consequence": "Mở tuyến mới",
            }],
        },
    }


def test_normalized_anchor_nested_schema_passes() -> None:
    raw = json.dumps(_anchor(), ensure_ascii=False).encode()
    result = validate_series_anchor_bytes(raw, load_prompt_contract())
    assert result.status == "PASS"
    assert result.checks["anchor_nested_schema"] == "PASS"


def test_anchor_rejects_cross_reference_to_unknown_character() -> None:
    anchor = _anchor()
    anchor["series_state"]["clues"][0]["known_by"] = ["missing"]
    result = validate_series_anchor_bytes(json.dumps(anchor).encode(), load_prompt_contract())
    assert result.status == "FAIL"
    assert any("known_by" in error for error in result.errors)


@pytest.mark.parametrize("episode", [None, "2", True])
def test_anchor_rejects_invalid_episode_design_number(episode: object) -> None:
    anchor = _anchor()
    designs = anchor["series_state"]["episode_designs"]
    designs.append({**designs[0], "episode": episode})

    result = validate_series_anchor_bytes(json.dumps(anchor).encode(), load_prompt_contract())

    assert result.status == "FAIL"
    assert any("episode_designs" in error for error in result.errors)


def test_package_status_keeps_completion_separate_from_gates() -> None:
    assert aggregate_package_status("PASS", "PASS", "PARTIAL") == ("PARTIAL", "FAIL")
    assert aggregate_package_status("PASS", "PASS", "COMPLETE") == ("PASS", "PASS")
    assert aggregate_package_status("PASS", "NOT_VERIFIED", "COMPLETE") == ("NOT_VERIFIED", "FAIL")
    assert aggregate_package_status("PASS", "FAIL", "COMPLETE") == ("FAIL", "FAIL")
