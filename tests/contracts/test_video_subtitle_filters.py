from pathlib import Path

from video.subtitle_filters import build_vf_filter, subtitle_background_to_ass


def test_slideshow_subtitle_filter_generates_frames_before_burning_subtitles() -> None:
    vf_filter = build_vf_filter("9x16", Path("story.srt"), pre_subtitle_fps=25)

    assert ",fps=25,subtitles=" in vf_filter
    assert vf_filter.index(",fps=25") < vf_filter.index(",subtitles=")
    assert "flags=lanczos" in vf_filter
    assert "setsar=1" in vf_filter
    assert "color_primaries=bt709" in vf_filter
    assert "BorderStyle=1" in vf_filter
    assert "BorderStyle=3" not in vf_filter


def test_subtitle_background_color_converts_to_ass_abgr() -> None:
    assert subtitle_background_to_ass("#000000", 50) == "&H80000000"
    assert subtitle_background_to_ass("#336699", 100) == "&H00996633"
    assert subtitle_background_to_ass("#336699", 0) == "&HFF996633"


def test_subtitle_filter_supports_fully_transparent_background(monkeypatch) -> None:
    monkeypatch.setenv("SUB_BACKGROUND_COLOR", "#336699")
    monkeypatch.setenv("SUB_BACKGROUND_OPACITY", "0")
    monkeypatch.delenv("SUB_FORCE_STYLE", raising=False)

    vf_filter = build_vf_filter("16x9", Path("story.srt"))

    assert "BorderStyle=1" in vf_filter
    assert "BorderStyle=3" not in vf_filter
    assert "OutlineColour=&HFF996633" in vf_filter
    assert "BackColour=&HFF996633" in vf_filter
