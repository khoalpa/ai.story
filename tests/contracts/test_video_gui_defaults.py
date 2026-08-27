from pathlib import Path

from video import config
from video.gui.settings import (
    build_subtitle_preview_html,
    default_subtitle_font_size,
    default_subtitle_position,
    should_update_subtitle_font_size,
    should_update_subtitle_position,
    subtitle_alignment_value,
)
from video.gui.tabs import (
    default_cover_path,
    default_scenes_directory,
    default_video_output,
    should_update_cover_path,
    should_update_scenes_directory,
    should_update_video_output,
)
from video.subtitle_fonts import (
    ARTISTIC_FONTS,
    BUNDLED_FONT_FILES,
    FONT_LICENSE_FILES,
    VIETNAMESE_HANDWRITING_FONTS,
    font_choice_label,
    font_preview_css,
)


def test_video_render_sidebar_defaults_to_youtube_slideshow() -> None:
    assert config.DEFAULT_RENDER_MODE == "slideshow"
    assert config.DEFAULT_ASPECT == "16x9"
    assert config.DEFAULT_SUBTITLE_FONT == "Playwrite VN"
    assert config.DEFAULT_SUBTITLE_FONT_SIZE == 12
    assert config.ENVIRONMENT_OVERLAY_INTENSITY == "normal"


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


def test_subtitle_styling_exposes_only_supported_controls() -> None:
    settings = Path("video/gui/settings.py").read_text(encoding="utf-8")

    assert '_SUBTITLE_POSITION_OPTIONS = ["bottom", "top"]' in settings
    assert '"Horizontal safe margin (%)"' in settings
    assert '"Vertical margin (%)"' in settings
    assert '"Subtitle force style override"' not in settings
    assert '"Transparent subtitle outline"' not in settings
    assert '"Subtitle shadow"' not in settings
    assert '"Subtitle margin left (%)"' not in settings
    assert '"Subtitle margin right (%)"' not in settings


def test_bundled_vietnamese_subtitle_fonts_are_available() -> None:
    assert VIETNAMESE_HANDWRITING_FONTS == ("Playwrite VN", "Patrick Hand", "Mali")
    assert ARTISTIC_FONTS == ("Dancing Script", "Pacifico", "Phudu")
    assert all(font_file.is_file() for font_file in BUNDLED_FONT_FILES.values())
    assert len(FONT_LICENSE_FILES) == len(BUNDLED_FONT_FILES)
    assert all(license_file.is_file() for license_file in FONT_LICENSE_FILES)
    assert font_choice_label("Playwrite VN").startswith("Vietnamese handwriting")
    assert font_choice_label("Pacifico").startswith("Artistic (short subtitles)")
    assert "@font-face" in font_preview_css("Playwrite VN")


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


def test_slideshow_subtitle_position_follows_aspect() -> None:
    assert default_subtitle_position("slideshow", "16x9") == "bottom"
    assert default_subtitle_position("slideshow", "9x16") == "top"
    assert should_update_subtitle_position(
        mode="slideshow",
        current="bottom",
        suggested="top",
        previous_suggestion="bottom",
    )
    assert not should_update_subtitle_position(
        mode="slideshow",
        current="center",
        suggested="top",
        previous_suggestion="bottom",
    )


def test_subtitle_alignment_dropdown_maps_to_ass_columns() -> None:
    assert subtitle_alignment_value("left") == 1
    assert subtitle_alignment_value("center") == 2
    assert subtitle_alignment_value("right") == 3
    assert subtitle_alignment_value("") == 2


def test_subtitle_preview_reflects_position_margins_and_aspect() -> None:
    preview = build_subtitle_preview_html(
        aspect="9x16",
        show_subtitles=True,
        position="top",
        font="Arial",
        font_size=8,
        text_color="#FFFFFF",
        text_opacity=100,
        outline=2,
        shadow=1,
        outline_color="#000000",
        outline_opacity=50,
        alignment=None,
        margin_l=3.0,
        margin_r=4.0,
        margin_v=6.0,
    )

    assert "aspect-ratio:9 / 16" in preview
    assert "left:3.0%;right:4.0%;top:6.0%" in preview
    assert "Alignment 6 · top · margin 6%" in preview
    assert "visibility:visible" in preview


def test_subtitle_preview_position_controls_vertical_anchor() -> None:
    preview = build_subtitle_preview_html(
        aspect="16x9",
        show_subtitles=False,
        position="bottom",
        font="Arial",
        font_size=12,
        text_color="#FFFFFF",
        text_opacity=100,
        outline=0,
        shadow=0,
        outline_color="#000000",
        outline_opacity=0,
        alignment=7,
        margin_l=2.0,
        margin_r=2.0,
        margin_v=5.0,
    )

    assert "text-align:left" in preview
    assert "bottom:5.0%" in preview
    assert "visibility:hidden" in preview
    assert "Subtitles hidden" in preview


def test_slideshow_output_default_follows_aspect() -> None:
    assert default_video_output("output", "16x9") == str(Path("output/video_landscape.mp4"))
    assert default_video_output("output", "9x16") == str(Path("output/video_portrait.mp4"))
    assert should_update_video_output(
        mode="slideshow",
        current="output/video_landscape.mp4",
        suggested="output/video_portrait.mp4",
        previous_suggestion="output/video_landscape.mp4",
    )
    assert not should_update_video_output(
        mode="slideshow",
        current="output/custom.mp4",
        suggested="output/video_portrait.mp4",
        previous_suggestion="output/video_landscape.mp4",
    )


def test_video_subtitles_are_visible_by_default_and_can_be_disabled_from_cli() -> None:
    from video.cli_entry import parse_args

    common = ["--audio", "story.wav", "--output", "video.mp4", "--mode", "static"]
    assert parse_args(common).show_subtitles is True
    assert parse_args([*common, "--no-show-subtitles"]).show_subtitles is False
    assert parse_args(common).environment_overlay_intensity == "normal"


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
