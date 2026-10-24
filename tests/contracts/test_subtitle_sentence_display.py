from pathlib import Path

import pytest

from video.media_quality import prepare_subtitle_for_video


def test_sentences_keep_source_bytes_and_original_cue_interval(tmp_path):
    source, display = tmp_path / "story.srt", tmp_path / "display.srt"
    original = "1\n00:00:01,123 --> 00:00:07,129\nCâu thứ nhất. Câu thứ hai! Câu thứ ba?\n"
    source.write_text(original, encoding="utf-8")
    original_bytes = source.read_bytes()
    prepared, changed = prepare_subtitle_for_video(source, display)
    assert changed and prepared == display
    assert source.read_bytes() == original_bytes
    blocks = display.read_text(encoding="utf-8").strip().split("\n\n")
    assert len(blocks) == 3
    times = [block.splitlines()[1].split(" --> ") for block in blocks]
    assert times[0][0] == "00:00:01,123" and times[-1][1] == "00:00:07,129"
    assert all(previous[1] == current[0] for previous, current in zip(times, times[1:]))


@pytest.mark.parametrize("text", ["TS. An ở TP. HCM.", "Mr. Smith is here.", "<i>Một. Hai.</i>", "Giá 3.14 đô."])
def test_abbreviations_decimals_and_styled_cues_are_preserved(tmp_path, text):
    source = tmp_path / "source.srt"
    source.write_text(f"1\n00:00:00,000 --> 00:00:06,000\n{text}\n", encoding="utf-8")
    assert prepare_subtitle_for_video(source, tmp_path / "display.srt") == (source, False)


def test_short_cues_do_not_flicker_and_source_cannot_be_overwritten(tmp_path):
    source = tmp_path / "source.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:00,200\nMột câu. Hai câu.\n", encoding="utf-8")
    assert prepare_subtitle_for_video(source, tmp_path / "display.srt") == (source, False)
    source.write_text("1\n00:00:00,000 --> 00:00:06,000\nMột câu. Hai câu.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="separately"):
        prepare_subtitle_for_video(source, source)


@pytest.mark.parametrize("mode", ["zone", "scene"])
@pytest.mark.parametrize("visible", [True, False])
def test_scene_timing_and_effects_use_original_srt_even_when_hidden(monkeypatch, tmp_path, mode, visible):
    from video import render_slideshow as renderer
    from video.zone_timeline import ZoneSegment

    source, display, picture = tmp_path / "original.srt", tmp_path / "display.srt", tmp_path / "opening.png"
    seen = {}

    def timeline(**kwargs):
        seen["timeline"] = kwargs["subtitle"]
        return [ZoneSegment("opening", picture, 0.0, 6.0)]

    def effects(**kwargs):
        seen["effects"] = kwargs["subtitle"]
        return []

    def video_filter(_aspect, subtitle, **kwargs):
        seen["display"] = subtitle
        return "null"

    monkeypatch.setattr(renderer, "validate_slideshow_inputs", lambda *_: [picture])
    monkeypatch.setattr(renderer, "collect_scene_images", lambda *_: [picture])
    monkeypatch.setattr(renderer, "resolve_slideshow_timeline_mode", lambda *_: mode)
    monkeypatch.setattr(renderer, "build_zone_segments", timeline)
    monkeypatch.setattr(renderer, "build_scene_segments", timeline)
    monkeypatch.setattr(renderer, "build_environment_segments", effects)
    monkeypatch.setattr(renderer, "build_environment_filter_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(renderer, "build_vf_filter", video_filter)
    monkeypatch.setattr(renderer, "run_ffmpeg", lambda *_args, **_kwargs: None)
    renderer.make_slideshow_video(
        audio=Path("audio.wav"), scenes_dir=tmp_path, aspect="16x9", output=tmp_path / "video.mp4",
        cover_first=False, outro_last=False, story_json=tmp_path / "story.json",
        visual_plan_json=tmp_path / "visual_plan.json", timeline_mode=mode,
        subtitle=display if visible else None, timeline_subtitle=source,
    )
    assert seen == {"timeline": source, "effects": source, "display": display if visible else None}
