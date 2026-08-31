from __future__ import annotations

import pytest

from studio.story_report import _select_reader_page, _validate_story, _zones_in_story


def _minimal_story() -> dict:
    return {"meta": {}, "characters": [], "outline": {}, "script": []}


def test_story_contract_accepts_required_sections() -> None:
    _validate_story(_minimal_story())


def test_story_contract_lists_missing_sections() -> None:
    with pytest.raises(ValueError, match="script"):
        _validate_story({"meta": {}})


def test_story_zones_use_narrative_order() -> None:
    script = [{"zone": "ENDING"}, {"zone": "OPENING"}, {"zone": "CUSTOM"}]
    assert _zones_in_story(script) == ["OPENING", "ENDING", "CUSTOM"]


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
    assert source.count("frame_ratio=(16, 9)") >= 2
    repetition = __import__("pathlib").Path("studio/story_repetition.py").read_text(encoding="utf-8")
    assert "frame_ratio=(16, 9)" in repetition
