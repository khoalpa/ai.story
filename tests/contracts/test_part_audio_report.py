from studio.audio_delivery_report import SubtitleCue, build_part_audio_report


def _story():
    return {"script": [
        {"id": "s0001", "zone": "OPENING", "scene_id": "sc001", "text": "Xin chào. Mời nghe!", "speed": 1.0, "pause_ms": 200},
        {"id": "s0002", "zone": "ENDING", "scene_id": "sc002", "text": "Tạm biệt.", "speed": 1.0, "pause_ms": 0},
    ]}


def _cues():
    return [SubtitleCue(1, 1000, 2000, "Xin chào."), SubtitleCue(2, 2500, 4000, "Mời nghe!"),
            SubtitleCue(3, 5000, 6500, "Tạm biệt.")]


def test_part_report_aggregates_multiple_cues_without_counting_gaps_as_speech():
    report = build_part_audio_report(_story(), _cues())
    assert report["aligned"]
    first, last = report["rows"]
    assert first["script_count"] == 1 and first["cue_count"] == 2
    assert first["speech_seconds"] == 2.5 and first["span_seconds"] == 3.0
    assert last["start_seconds"] == 5.0 and last["end_seconds"] == 6.5
    scenes = build_part_audio_report(_story(), _cues(), group_by="scene_id")
    assert [row["part"] for row in scenes["rows"]] == ["sc001", "sc002"]


def test_equal_cue_counts_do_not_validate_different_or_reordered_content():
    cues = [SubtitleCue(1, 0, 1000, "Tạm biệt."), SubtitleCue(2, 2000, 3000, "Xin chào. Mời nghe!")]
    report = build_part_audio_report(_story(), cues)
    assert not report["aligned"]
    assert all(row["speech_seconds"] is None and row["status"] == "Chưa khớp nguồn" for row in report["rows"])


def test_missing_or_overlapping_subtitles_do_not_invent_actual_measurements():
    assert all(row["speech_seconds"] is None for row in build_part_audio_report(_story(), [])["rows"])
    cues = _cues()
    cues[1] = SubtitleCue(2, 1500, 4000, "Mời nghe!")
    assert not build_part_audio_report(_story(), cues)["aligned"]


def test_story_studio_renders_part_report_with_missing_and_matched_data():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
from pathlib import Path
import streamlit as st
from studio.audio_delivery_report import render_audio_delivery
render_audio_delivery(st.session_state['data'], Path('.'))
''', default_timeout=20)
    app.session_state["data"] = {"story": _story(), "subtitle": _cues()}
    app.run()
    assert not app.exception
    assert any("Lời thoại theo SRT (s)" in frame.value.columns for frame in app.dataframe)
    app.radio(key="story_audio_group_by").set_value("Cảnh").run()
    assert not app.exception
    app.session_state["data"] = {"story": _story()}
    app.run()
    assert not app.exception
