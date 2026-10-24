from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from video.gui.media_preview import _build_test_slideshow_segments


@pytest.fixture
def preview_inputs(tmp_path):
    for name in ("cover.png", "opening.png", "outro.png"):
        Image.new("RGB", (32, 18), "blue").save(tmp_path / name)
    audio = tmp_path / "story.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * 8000)
    return {"scenes_dir": tmp_path, "cover": tmp_path / "cover.png", "audio": audio,
            "output": tmp_path / "video.mp4", "image_readiness": None, "summary": {}}


@pytest.mark.parametrize("endpoints", [True, False])
def test_preview_shows_inputs_gallery_and_endpoint_settings(preview_inputs, endpoints):
    app = AppTest.from_string('''
import streamlit as st
from video.gui.media_preview import render_video_preview
render_video_preview(st.session_state.settings, inputs=st.session_state.inputs,
                     render_readiness=lambda _: st.info("Readiness checked"))
''')
    app.session_state["inputs"] = preview_inputs
    app.session_state["settings"] = {
        "mode": "slideshow", "slideshow_timeline_mode": "fixed", "slideshow_match_audio": False,
        "cover_first": endpoints, "outro_last": endpoints, "duration_per_image": 20,
    }
    app.run()
    assert not app.exception
    assert any("Slideshow image order" == heading.value for heading in app.subheader)
    table = app.dataframe[0].value.set_index("input")
    assert table.loc["Audio", "status"] == "ready"
    assert table.loc["Video output", "status"] == "pending"
    assert len(app.get("image")) >= 1
    messages = " ".join(item.value for kind in (app.info, app.success) for item in kind)
    assert ("Cover-first is active" if endpoints else "Cover-first is disabled") in messages
    assert ("End screen is active" if endpoints else "End screen is disabled") in messages


def test_preview_reports_missing_media_without_throwing(tmp_path):
    app = AppTest.from_string('''
import streamlit as st
from video.gui.media_preview import render_video_preview
render_video_preview({"mode": "slideshow"}, inputs=st.session_state.inputs,
                     render_readiness=lambda _: None)
''')
    app.session_state["inputs"] = {"scenes_dir": tmp_path, "cover": tmp_path / "absent.png",
                                    "audio": None, "image_readiness": None, "errors": ["Audio is missing"]}
    app.run()
    assert not app.exception
    assert any("No playable audio" in item.value for item in app.info)
    assert any("cover is unavailable" in item.value for item in app.warning)
    assert any("outro.png was not found" in item.value for item in app.warning)


def test_static_preview_shows_cover(preview_inputs):
    app = AppTest.from_string('''
import streamlit as st
from video.gui.media_preview import render_video_preview
render_video_preview({"mode": "static"}, inputs=st.session_state.inputs,
                     render_readiness=lambda _: None)
''')
    app.session_state["inputs"] = preview_inputs
    app.run()
    assert not app.exception
    assert len(app.get("image")) == 1


def test_slideshow_preview_preserves_endpoint_timing(preview_inputs):
    inputs = dict(preview_inputs, audio=None)
    segments, error = _build_test_slideshow_segments(inputs, {"slideshow_timeline_mode": "fixed", "duration_per_image": 20})
    assert error is None
    assert segments[0].image == inputs["cover"]
    assert segments[-1].image == Path(inputs["scenes_dir"]) / "outro.png"
    assert segments[0].start == 0
    assert segments[-1].end == 20
    assert all(left.end == right.start for left, right in zip(segments, segments[1:]))


def test_invalid_preview_configuration_returns_readable_error(preview_inputs):
    segments, error = _build_test_slideshow_segments(preview_inputs, {"slideshow_timeline_mode": "fixed", "duration_per_image": "invalid"})
    assert not segments
    assert "invalid" in error
