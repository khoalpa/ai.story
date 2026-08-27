from pathlib import Path

from video.subtitle_filters import (
    apply_authoritative_subtitle_placement,
    build_vf_filter,
    resolve_subtitle_alignment,
    subtitle_background_to_ass,
    subtitle_margin_percent_to_ass_units,
    subtitle_play_resolution,
    subtitle_text_color_to_ass,
)


def test_slideshow_subtitle_filter_generates_frames_before_burning_subtitles() -> None:
    vf_filter = build_vf_filter("9x16", Path("story.srt"), pre_subtitle_fps=25)

    assert ",fps=25,subtitles=" in vf_filter
    assert vf_filter.index(",fps=25") < vf_filter.index(",subtitles=")
    assert "flags=lanczos" in vf_filter
    assert "setsar=1" in vf_filter
    assert "color_primaries=bt709" in vf_filter
    assert "BorderStyle=1" in vf_filter
    assert "BorderStyle=3" not in vf_filter
    assert "fontsdir=" in vf_filter


def test_hidden_subtitles_leave_video_filter_without_subtitle_burn_in() -> None:
    vf_filter = build_vf_filter("9x16", None, pre_subtitle_fps=25)

    assert "subtitles=" not in vf_filter
    assert "scale=1080:1920" in vf_filter


def test_static_video_still_builds_render_command_when_subtitles_are_hidden(monkeypatch) -> None:
    from video import render_static

    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(render_static, "validate_static_inputs", lambda *_args: None)
    monkeypatch.setattr(render_static, "ensure_output_dir", lambda *_args: None)
    monkeypatch.setattr(render_static, "get_media_duration_seconds", lambda *_args: 1.0)
    monkeypatch.setattr(
        render_static,
        "run_ffmpeg",
        lambda command, **_kwargs: captured.setdefault("command", command),
    )

    render_static.make_static_video(
        audio=Path("audio.wav"),
        cover=Path("cover.png"),
        aspect="9x16",
        output=Path("video.mp4"),
        subtitle=None,
    )

    command = captured["command"]
    video_filter = command[command.index("-vf") + 1]
    assert "subtitles=" not in video_filter
    assert command[-1] == "video.mp4"


def test_subtitle_background_color_converts_to_ass_abgr() -> None:
    assert subtitle_background_to_ass("#000000", 50) == "&H80000000"
    assert subtitle_background_to_ass("#336699", 100) == "&H00996633"
    assert subtitle_background_to_ass("#336699", 0) == "&HFF996633"


def test_subtitle_text_color_converts_to_opaque_ass_abgr() -> None:
    assert subtitle_text_color_to_ass("#FFFFFF") == "&H00FFFFFF"
    assert subtitle_text_color_to_ass("#336699") == "&H00996633"
    assert subtitle_text_color_to_ass("#FFFFFF", 50) == "&H80FFFFFF"


def test_subtitle_margin_percent_scales_with_ass_play_resolution() -> None:
    assert subtitle_margin_percent_to_ass_units(2, 384) == 8
    assert subtitle_margin_percent_to_ass_units(2, 288) == 6


def test_subtitle_margin_uses_ass_file_play_resolution(tmp_path) -> None:
    subtitle = tmp_path / "story.ass"
    subtitle.write_text("[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n", encoding="utf-8")

    assert subtitle_play_resolution(subtitle) == (1920, 1080)


def test_subtitle_filter_applies_selected_font_and_text_color(monkeypatch) -> None:
    monkeypatch.setenv("SUB_FONT", "Times New Roman")
    monkeypatch.setenv("SUB_TEXT_COLOR", "#336699")
    monkeypatch.setenv("SUB_TEXT_OPACITY", "50")
    monkeypatch.delenv("SUB_FORCE_STYLE", raising=False)

    vf_filter = build_vf_filter("16x9", Path("story.srt"))

    assert "FontName=Times New Roman" in vf_filter
    assert "PrimaryColour=&H80996633" in vf_filter


def test_subtitle_filter_supports_fully_transparent_background(monkeypatch) -> None:
    monkeypatch.setenv("SUB_BACKGROUND_COLOR", "#336699")
    monkeypatch.setenv("SUB_BACKGROUND_OPACITY", "0")
    monkeypatch.delenv("SUB_FORCE_STYLE", raising=False)

    vf_filter = build_vf_filter("16x9", Path("story.srt"))

    assert "BorderStyle=1" in vf_filter
    assert "BorderStyle=3" not in vf_filter
    assert "OutlineColour=&HFF996633" in vf_filter
    assert "BackColour=&HFF996633" in vf_filter


def test_subtitle_position_top_anchors_text_at_top(monkeypatch) -> None:
    monkeypatch.setenv("SUB_POSITION", "top")
    monkeypatch.delenv("SUB_ALIGNMENT", raising=False)
    monkeypatch.delenv("SUB_MARGIN_V", raising=False)
    monkeypatch.delenv("SUB_FORCE_STYLE", raising=False)

    vf_filter = build_vf_filter("9x16", Path("story.srt"))

    assert "Alignment=6" in vf_filter
    assert "MarginV=6" in vf_filter


def test_subtitle_position_middle_anchors_text_at_center(monkeypatch) -> None:
    monkeypatch.setenv("SUB_POSITION", "middle")
    monkeypatch.delenv("SUB_ALIGNMENT", raising=False)
    monkeypatch.delenv("SUB_MARGIN_V", raising=False)
    monkeypatch.delenv("SUB_FORCE_STYLE", raising=False)

    vf_filter = build_vf_filter("9x16", Path("story.srt"))

    assert "Alignment=10" in vf_filter
    assert "MarginV=6" in vf_filter


def test_subtitle_position_bottom_anchors_text_at_bottom(monkeypatch) -> None:
    monkeypatch.setenv("SUB_POSITION", "bottom")
    monkeypatch.delenv("SUB_ALIGNMENT", raising=False)
    monkeypatch.delenv("SUB_MARGIN_V", raising=False)
    monkeypatch.delenv("SUB_FORCE_STYLE", raising=False)

    vf_filter = build_vf_filter("9x16", Path("story.srt"))

    assert "Alignment=2" in vf_filter
    assert "MarginV=6" in vf_filter


def test_subtitle_position_remains_authoritative_over_alignment_override(monkeypatch) -> None:
    monkeypatch.setenv("SUB_POSITION", "top")
    monkeypatch.setenv("SUB_ALIGNMENT", "5")
    monkeypatch.delenv("SUB_FORCE_STYLE", raising=False)

    vf_filter = build_vf_filter("9x16", Path("story.srt"))

    assert resolve_subtitle_alignment("top", "5", srt_compat=True) == 6
    assert "Alignment=6" in vf_filter


def test_gui_placement_overrides_conflicting_custom_force_style(monkeypatch) -> None:
    monkeypatch.setenv("SUB_POSITION", "top")
    monkeypatch.setenv("SUB_ALIGNMENT", "2")
    monkeypatch.setenv("SUB_MARGIN_V", "2")
    monkeypatch.setenv(
        "SUB_FORCE_STYLE",
        "FontName=Arial,Alignment=5,MarginV=144,PrimaryColour=&H00FFFFFF",
    )

    vf_filter = build_vf_filter("9x16", Path("story.srt"))

    assert "Alignment=6" in vf_filter
    assert "Alignment=5" not in vf_filter
    assert "MarginV=6" in vf_filter
    assert "MarginV=144" not in vf_filter


def test_authoritative_placement_preserves_non_placement_custom_style() -> None:
    merged = apply_authoritative_subtitle_placement(
        "FontName=Tahoma,Alignment=5,Outline=3",
        alignment=8,
        margin_l=8,
        margin_r=8,
        margin_v=6,
    )

    assert merged == "FontName=Tahoma,Outline=3,Alignment=8,MarginV=6,MarginL=8,MarginR=8"
