from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_audio_batch_gui_exposes_continue_on_error() -> None:
    content = (ROOT / "audio" / "gui" / "batch.py").read_text(encoding="utf-8")
    assert "Continue on batch error" in content
    assert "continue_on_error=bool(continue_on_error)" in content
    assert "ffmpeg_exe=str(settings.get(\"ffmpeg_exe\")" in content
    assert "ffprobe_exe=str(settings.get(\"ffprobe_exe\")" in content

