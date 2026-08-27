from __future__ import annotations

from pathlib import Path

import pytest

from audio.exceptions import ValidationError
from audio.gui.service import validate_plain_text
from audio.render_audio_app import create_default_app_request, run_render_audio_app
from audio.render_events import AppValidationCompletedEvent


def test_gui_validation_keeps_warning_count_separate_from_exit_code() -> None:
    exit_code, errors, warnings_count = validate_plain_text(
        "SCRIPT:\n// LỜI CHÀO\n[NARRATOR][NORMAL][VI] Xin chào."
    )

    assert exit_code == 0
    assert errors == ()
    assert warnings_count > 0


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
