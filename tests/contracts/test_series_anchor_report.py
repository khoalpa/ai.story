from __future__ import annotations

from copy import deepcopy

import pytest

from studio.series_anchor_report import (
    _series_anchor_view,
    _status_text,
    _validate_series_anchor,
)


def _normalized_anchor() -> dict:
    return {
        "schema_version": "4.1.3", "series_title": "Series thử", "last_completed_episode": 1,
        "characters": [{"character_id": "c001", "name": "Linh", "established_facts": [], "known_facts": []}],
        "canon_facts": [{"fact_id": "f001", "text": "Sự kiện", "established_episode": 1}],
        "open_threads": [{"thread_id": "t001", "description": "Câu hỏi mở", "clues": []}],
        "resolved_threads": [],
        "episode_summaries": [{"episode": 1, "summary": "Tập một"}],
        "series_state": {
            "status": "ACTIVE",
            "next_episode_contract": {"episode": 2, "premise": "Điều tra tiếp", "required_thread_ids": ["t001"], "forbidden_resolutions": []},
            "milestones": [], "clues": [], "consequences": [], "visual_locks": [],
            "episode_designs": [{"episode": 1, "central_question": "Chuyện gì?", "case_type": "OTHER", "clue_media": ["vật chứng"], "decisive_choice": "Tìm hiểu", "ending_consequence": "Mở tuyến"}],
        },
    }


def _legacy_anchor() -> dict:
    return {
        "schema_version": "4.1.3",
        "series": {"title": "Series cũ", "last_completed_episode": 0, "status": "UNKNOWN", "next_episode_contract": None},
        "canon": {"characters": [], "facts": [], "open_threads": [], "resolved_threads": []},
        "continuity": {"milestones": [], "clues": [], "consequences": [], "visual_locks": [], "episode_designs": []},
        "episode_ledger": {"last_completed_episode": 0, "episodes": []},
        "canon_change_log": [],
    }


@pytest.mark.parametrize("anchor", [_normalized_anchor(), _legacy_anchor()])
def test_series_anchor_contract_accepts_supported_shapes(anchor: dict) -> None:
    _validate_series_anchor(anchor)


def test_normalized_anchor_projects_to_series_view() -> None:
    view = _series_anchor_view(_normalized_anchor())
    assert view["series"]["title"] == "Series thử"
    assert view["continuity"]["latest_episode"] == 1
    assert view["continuity"]["open_threads"][0]["thread_id"] == "t001"
    assert view["episode_ledger"][0]["episode_number"] == 1


def test_series_anchor_rejects_hybrid_schema() -> None:
    hybrid = deepcopy(_normalized_anchor())
    hybrid["canon"] = {}
    with pytest.raises(ValueError, match="closed schema"):
        _validate_series_anchor(hybrid)


def test_series_anchor_contract_reports_canonical_errors() -> None:
    broken = _normalized_anchor()
    broken["series_state"]["next_episode_contract"]["required_thread_ids"] = ["missing"]
    with pytest.raises(ValueError, match="required_thread_ids"):
        _validate_series_anchor(broken)


def test_status_labels_are_human_readable() -> None:
    assert _status_text("active") == "Đang phát triển"
    assert _status_text("custom_state") == "Custom State"
