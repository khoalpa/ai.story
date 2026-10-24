from __future__ import annotations

from pathlib import Path

import pytest

from audio.exceptions import ValidationError
from audio.gui.service import validate_plain_text
from audio.render_audio_app import create_default_app_request, run_render_audio_app
from audio.render_events import AppValidationCompletedEvent
from audio.validate_plain_script import validate_script


def test_gui_validation_keeps_warning_count_separate_from_exit_code() -> None:
    exit_code, errors, warnings_count = validate_plain_text(
        "SCRIPT:\n// LỜI CHÀO\n[NARRATOR][NORMAL][VI] Xin chào."
    )

    assert exit_code == 0
    assert errors == ()
    assert warnings_count > 0


def test_standalone_pause_directive_does_not_warn_about_missing_voice() -> None:
    result = validate_script([
        "SCRIPT:",
        "// LỜI CHÀO",
        "[NARRATOR][RATE=+0%][VI] Xin chào.",
        "[PAUSE=450ms]",
        "[FEMALE][RATE=+0%][VI] Chào bạn.",
    ])

    assert result.ok
    assert result.stats.no_voice_tag_lines == 0
    assert not any("không có tag giọng" in warning.message for warning in result.warnings)


def test_real_dialogue_without_voice_tag_still_warns() -> None:
    result = validate_script(["SCRIPT:", "// LỜI CHÀO", "[VI] Xin chào."])
    assert result.stats.no_voice_tag_lines == 1
    assert any("không có tag giọng" in warning.message for warning in result.warnings)


def test_render_rejects_invalid_script_before_creating_output(tmp_path: Path) -> None:
    input_path = tmp_path / "invalid.txt"
    output_dir = tmp_path / "output"
    input_path.write_text("This is not a plain audio script.", encoding="utf-8")
    request = create_default_app_request(input_path, output_dir)
    events = []

    with pytest.raises(ValidationError, match="Plain script validation failed"):
        run_render_audio_app(
            request,
            ffmpeg_exe="ffmpeg-does-not-need-to-exist",
            ffprobe_exe="ffprobe-does-not-need-to-exist",
            event_sink=events.append,
        )

    assert not output_dir.exists()
    validation_events = [event for event in events if isinstance(event, AppValidationCompletedEvent)]
    assert len(validation_events) == 1
    assert validation_events[0].exit_code == 1
    assert validation_events[0].errors
