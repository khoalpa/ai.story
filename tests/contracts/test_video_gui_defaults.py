from video import config


def test_video_render_sidebar_defaults_to_youtube_slideshow() -> None:
    assert config.DEFAULT_RENDER_MODE == "slideshow"
    assert config.DEFAULT_ASPECT == "16x9"
    assert config.DEFAULT_SUBTITLE_FONT_SIZE == 12
