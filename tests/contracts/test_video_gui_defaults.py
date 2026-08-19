from pathlib import Path

from video import config
from video.gui.settings import default_subtitle_font_size, should_update_subtitle_font_size
from video.gui.tabs import (
    default_cover_path,
    default_scenes_directory,
    should_update_cover_path,
    should_update_scenes_directory,
)


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


def test_video_direct_input_path_defaults() -> None:
    state = Path("video/gui/state.py").read_text(encoding="utf-8")
    settings = Path("video/gui/settings.py").read_text(encoding="utf-8")

    assert 'VIDEO_AUDIO_INPUT_KEY: "output/story.wav"' in state
    assert 'VIDEO_INPUT_COVER_PATH_KEY: "output/landscape/cover.png"' in state
    assert 'st.text_input("Input root", value="output")' in settings
    assert 'st.text_input("Output directory", value="output")' in settings


def test_slideshow_scenes_default_follows_aspect() -> None:
    assert default_scenes_directory("output", "16x9") == str(Path("output") / "landscape")
    assert default_scenes_directory("output", "9x16") == str(Path("output") / "portrait")
    assert default_scenes_directory("output", "6x16") == str(Path("output") / "portrait")


def test_slideshow_cover_default_follows_aspect() -> None:
    assert default_cover_path("output", "16x9") == str(Path("output/landscape/cover.png"))
    assert default_cover_path("output", "9x16") == str(Path("output/portrait/cover.png"))
    assert not should_update_cover_path(
        mode="slideshow",
        current="output/landscape/cover.png",
        suggested="output/landscape/cover.png",
        previous_suggestion="output/landscape/cover.png",
    )
    assert should_update_cover_path(
        mode="slideshow",
        current="output/landscape/cover.png",
        suggested="output/portrait/cover.png",
        previous_suggestion="output/landscape/cover.png",
    )


def test_slideshow_subtitle_font_size_follows_aspect() -> None:
    assert default_subtitle_font_size("slideshow", "16x9") == 12
    assert default_subtitle_font_size("slideshow", "9x16") == 8
    assert should_update_subtitle_font_size(
        mode="slideshow", current=12, suggested=8, previous_suggestion=12
    )
    assert not should_update_subtitle_font_size(
        mode="slideshow", current=10, suggested=8, previous_suggestion=12
    )


def test_scenes_default_sync_is_idempotent_after_widget_creation() -> None:
    assert not should_update_scenes_directory(
        mode="slideshow",
        current="output/landscape",
        suggested="output/landscape",
        previous_suggestion="output/landscape",
    )
    assert should_update_scenes_directory(
        mode="slideshow",
        current="output/landscape",
        suggested="output/portrait",
        previous_suggestion="output/landscape",
    )
