from pathlib import Path

from video.subtitle_filters import build_vf_filter


def test_slideshow_subtitle_filter_generates_frames_before_burning_subtitles() -> None:
    vf_filter = build_vf_filter("9x16", Path("story.srt"), pre_subtitle_fps=25)

    assert ",fps=25,subtitles=" in vf_filter
    assert vf_filter.index(",fps=25") < vf_filter.index(",subtitles=")
