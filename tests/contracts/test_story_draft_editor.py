import hashlib
import json
from copy import deepcopy

import pytest

from audio.gui.story_editor import editor_image, save_story_draft, update_story_item
from audio.story_package_v416 import ZONES, parse_story_text


def story_fixture():
    return {
        "schema_version": "4.1.3",
        "meta": {"title": "Truyện mẫu", "series": None, "episode": 1, "author": "Test", "channel": "Test",
                 "profile": "ADULT_STANDARD", "age_band": "18+", "language": "vi", "genre": "Đời sống",
                 "tone": "Nhẹ nhàng", "target_minutes": 1, "estimated_minutes": None, "timing_method": "estimate", "tags": ["test"]},
        "characters": [{"character_id": "c001", "name": "An", "age": 20, "role": "Chính", "appearance": "Áo xanh",
                        "personality": "Vui", "voice_note": "giọng nam"}],
        "outline": [{"scene_id": "sc001", "summary": "Một ngày", "change": "An trở về", "setup_or_payoff": None}],
        "script": [{"id": f"s{index:04d}", "zone": zone, "scene_id": "sc001", "speaker": "narrator",
                    "text": f"Câu thoại {index}.", "emotion": "neutral", "speed": 1.0, "pause_ms": 0, "ambience": None}
                   for index, zone in enumerate(ZONES, 1)],
    }


def test_editor_preserves_closed_schema_ids_order_and_untouched_fields():
    source = story_fixture()
    expected = deepcopy(source)
    expected["script"][1].update(text="Lời mới.", speed=0.95, speaker="c001")
    result = update_story_item(json.dumps(source), "s0002", {"text": "Lời mới.", "speed": 0.95, "speaker": "c001"})
    assert parse_story_text(result) == expected


@pytest.mark.parametrize("change", [{"id": "s999"}, {"scene_id": "sc009"}, {"zone": "CLIMAX"},
                                    {"speed": 0}, {"text": " "}, {"speaker": "c999"}, {"pause_ms": -1}])
def test_editor_rejects_structural_changes_or_invalid_values(change):
    with pytest.raises(ValueError):
        update_story_item(json.dumps(story_fixture()), "s0002", change)


def test_editor_preview_never_reads_images_outside_asset_directory(tmp_path):
    (tmp_path / "landscape").mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"image")
    (tmp_path / "visual_plan.json").write_text(json.dumps({"image_mode": "SCENE", "assets": [
        {"basename": "../outside.png", "source_script_ids": ["s001"]},
    ]}))
    assert editor_image(tmp_path, "s001", "GREETING") is None


def test_draft_form_updates_json_survives_reruns_and_leaves_source_on_disk(tmp_path):
    from streamlit.testing.v1 import AppTest

    source = json.dumps(story_fixture(), ensure_ascii=False)
    story_path = tmp_path / "story.json"
    story_path.write_text(source, encoding="utf-8")
    before = story_path.read_bytes()
    app = AppTest.from_string("import streamlit as st\nfrom audio.gui.workspace import render_workspace_tab\nif st.checkbox('Mở workspace', value=True):\n    render_workspace_tab()", default_timeout=20)
    app.session_state["canonical_json_text"] = source
    app.session_state["canonical_editor"] = source
    app.run()
    assert not app.exception
    next(widget for widget in app.text_area if widget.label == "Lời thoại").set_value("Bản nháp đã chỉnh.")
    next(widget for widget in app.button if widget.label == "Lưu bản nháp").click().run()
    assert not app.exception
    assert parse_story_text(app.session_state["canonical_json_text"])["script"][0]["text"] == "Bản nháp đã chỉnh."
    app.run()
    assert not app.exception
    assert app.session_state["audio_story_editor_is_draft"] is True
    assert story_path.read_bytes() == before
    next(widget for widget in app.checkbox if widget.label == "Mở workspace").uncheck().run()
    next(widget for widget in app.checkbox if widget.label == "Mở workspace").check().run()
    assert not app.exception
    assert parse_story_text(app.session_state["canonical_editor"])["script"][0]["text"] == "Bản nháp đã chỉnh."
    manual = parse_story_text(app.session_state["canonical_editor"])
    manual["script"][0]["text"] = "Sửa trực tiếp trong JSON."
    next(widget for widget in app.text_area if widget.label == "Canonical JSON").set_value(json.dumps(manual)).run()
    assert not app.exception
    assert parse_story_text(app.session_state["canonical_json_text"])["script"][0]["text"] == "Sửa trực tiếp trong JSON."


def test_form_from_an_older_source_cannot_overwrite_new_content():
    source = json.dumps(story_fixture())
    current = update_story_item(source, "s0001", {"text": "Nguồn vừa đổi."})
    state = {"canonical_editor": current, "canonical_json_text": current}
    save_story_draft(state, "s0001", "old_form", hashlib.sha256(source.encode()).hexdigest())
    assert state["canonical_editor"] == current
    assert "Nguồn vừa thay đổi" in state["audio_story_editor_error"]
