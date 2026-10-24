from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.story_report import (
    _character_reference,
    _outline_items,
    _select_reader_page,
    _validate_story,
    _zones_in_story,
)


def _minimal_story() -> dict:
    return {"meta": {}, "characters": [], "outline": [], "script": []}


def test_story_contract_accepts_required_sections() -> None:
    _validate_story(_minimal_story())


def test_story_contract_lists_missing_sections() -> None:
    with pytest.raises(ValueError, match="script"):
        _validate_story({"meta": {}})


def test_story_zones_use_narrative_order() -> None:
    script = [{"zone": "ENDING"}, {"zone": "OPENING"}, {"zone": "CUSTOM"}]
    assert _zones_in_story(script) == ["OPENING", "ENDING", "CUSTOM"]


def test_story_outline_uses_v416_scene_array() -> None:
    story = _minimal_story()
    story["outline"] = [{
        "scene_id": "sc001", "summary": "Mở truyện", "change": "Câu hỏi xuất hiện",
        "setup_or_payoff": "Đặt chi tiết hồi đáp",
    }]
    assert _outline_items(story) == story["outline"]


def test_story_outline_rejects_old_object_shape() -> None:
    story = _minimal_story()
    story["outline"] = {"opening": "Mở truyện"}
    with pytest.raises(ValueError, match="outline"):
        _validate_story(story)


def test_character_reference_comes_from_v416_visual_plan(tmp_path: Path) -> None:
    (tmp_path / "characters").mkdir()
    expected = tmp_path / "characters" / "c001.png"
    expected.write_bytes(b"png fixture")
    (tmp_path / "visual_plan.json").write_text(json.dumps({
        "characters": [{
            "character_id": "c001", "planned_reference_path": "characters/c001.png",
            "reference_path": "characters/c001.png", "reference_status": "READY",
            "description_lock": "Mai",
        }],
    }), encoding="utf-8")

    path, status, relative = _character_reference(tmp_path, "c001")
    assert path == expected.resolve()
    assert status == "READY"
    assert relative == "characters/c001.png"


def test_character_reference_does_not_treat_pending_path_as_ready(tmp_path: Path) -> None:
    (tmp_path / "visual_plan.json").write_text(json.dumps({
        "characters": [{
            "character_id": "c001", "planned_reference_path": "characters/c001.png",
            "reference_path": None, "reference_status": "PENDING", "description_lock": "Mai",
        }],
    }), encoding="utf-8")
    assert _character_reference(tmp_path, "c001") == (None, "PENDING", "")


def test_single_page_reader_does_not_render_degenerate_slider() -> None:
    class StreamlitStub:
        def select_slider(self, *args: object, **kwargs: object) -> int:
            raise AssertionError("A one-page reader must not render a slider")

    assert _select_reader_page(StreamlitStub(), page_count=1, zone="GREETING") == 1


def test_multi_page_reader_renders_page_slider() -> None:
    class StreamlitStub:
        def select_slider(self, label: str, **kwargs: object) -> int:
            assert label == "Trang"
            assert kwargs["options"] == [1, 2, 3]
            return 2

    assert _select_reader_page(StreamlitStub(), page_count=3, zone="GREETING") == 2


def test_story_reader_includes_repetition_tab() -> None:
    source = __import__("pathlib").Path("studio/story_report.py").read_text(encoding="utf-8")
    assert '"Lặp câu"' in source
    assert "render_repetition_report(report," in source


def test_story_reader_centers_zone_thumbnail_at_half_content_width() -> None:
    source = __import__("pathlib").Path("studio/story_report.py").read_text(encoding="utf-8")
    assert "_left_space, image_column, _right_space = st.columns([1, 2, 1])" in source
    assert "with image_column:" in source


def test_story_content_images_share_landscape_display_frame() -> None:
    source = __import__("pathlib").Path("studio/story_report.py").read_text(encoding="utf-8")
    assert "_render_context_gallery" in source
    assert "frame_ratio=(16, 9)" in source
    repetition = __import__("pathlib").Path("studio/story_repetition.py").read_text(encoding="utf-8")
    assert "frame_ratio=(16, 9)" in repetition
