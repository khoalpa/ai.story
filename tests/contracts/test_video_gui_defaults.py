from pathlib import Path

from video import config


def test_video_render_sidebar_defaults_to_youtube_slideshow() -> None:
    assert config.DEFAULT_RENDER_MODE == "slideshow"
    assert config.DEFAULT_ASPECT == "16x9"
    assert config.DEFAULT_SUBTITLE_FONT_SIZE == 12


def test_video_assets_use_direct_input_only() -> None:
    tabs = Path("video/gui/tabs.py").read_text(encoding="utf-8")
    settings = Path("video/gui/settings.py").read_text(encoding="utf-8")

    assert '"Input cover image"' in tabs
    assert '"Input scenes directory"' in tabs
    assert "Cover image source" not in tabs
    assert "Scenes directory source" not in tabs
    assert "Image handoff manifest" not in tabs
    assert "Asset profile" not in settings
    assert "Profile root" not in settings
