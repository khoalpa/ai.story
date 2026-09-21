from __future__ import annotations

from pathlib import Path

import pytest

from video.clip_concat import (
    ConcatClipsRequest,
    discover_clips,
    validate_concat_request,
    write_clip_concat_list,
)
from video.clip_probe import ClipMetadata, clips_are_copy_compatible
from video.command_builders import build_clip_concat_cmd, build_clip_normalize_cmd


def _metadata(path: Path, **changes: object) -> ClipMetadata:
    values = {
        "path": path,
        "duration": 2.0,
        "video_codec": "h264",
        "width": 1920,
        "height": 1080,
        "pixel_format": "yuv420p",
        "frame_rate": 30.0,
        "time_base": "1/15360",
        "has_audio": True,
        "audio_codec": "aac",
        "audio_sample_rate": 48000,
        "audio_channels": 2,
    }
    values.update(changes)
    return ClipMetadata(**values)  # type: ignore[arg-type]


def test_discover_clips_uses_natural_number_order(tmp_path: Path) -> None:
    for name in ("clip_10.mp4", "clip_2.mp4", "clip_0001.mp4", "ignore.txt"):
        (tmp_path / name).write_bytes(b"x")

    assert [path.name for path in discover_clips(tmp_path)] == [
        "clip_0001.mp4", "clip_2.mp4", "clip_10.mp4"
    ]


def test_copy_compatibility_checks_video_and_optional_audio(tmp_path: Path) -> None:
    first = _metadata(tmp_path / "1.mp4")
    different_audio = _metadata(tmp_path / "2.mp4", audio_sample_rate=44100)

    assert not clips_are_copy_compatible([first, different_audio])
    assert clips_are_copy_compatible([first, different_audio], include_audio=False)
    assert not clips_are_copy_compatible(
        [first, _metadata(tmp_path / "3.mp4", frame_rate=24.0)], include_audio=False
    )


def test_concat_manifest_escapes_and_uses_absolute_paths(tmp_path: Path) -> None:
    clip = tmp_path / "clip one's.mp4"
    clip.write_bytes(b"x")
    manifest = tmp_path / "clips.ffconcat"

    write_clip_concat_list([clip], manifest)

    text = manifest.read_text(encoding="utf-8")
    assert text.startswith("ffconcat version 1.0\n")
    assert "clip one\\'s.mp4" in text
    assert str(tmp_path.resolve()).replace("\\", "\\\\") in text


def test_concat_commands_preserve_or_supply_audio(tmp_path: Path) -> None:
    concat = build_clip_concat_cmd(
        ffmpeg_exe="ffmpeg",
        concat_list=tmp_path / "clips.ffconcat",
        output=tmp_path / "final.mp4",
        audio_mode="mute",
    )
    assert "-an" in concat
    assert concat[concat.index("-c") + 1] == "copy"

    normalize = build_clip_normalize_cmd(
        ffmpeg_exe="ffmpeg", clip=tmp_path / "silent.mp4",
        output=tmp_path / "normalized.mp4", duration=3.0, has_audio=False,
        audio_mode="keep", width=1920, height=1080, fps=30,
        video_codec="libx264", preset="medium", crf=20,
        pixel_format="yuv420p", audio_codec="aac", audio_bitrate="192k",
    )
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in normalize
    assert normalize[normalize.index("-map", normalize.index("-map") + 1) + 1] == "1:a:0"


def test_concat_request_rejects_output_as_input(tmp_path: Path) -> None:
    clip = tmp_path / "clip_0001.mp4"
    clip.write_bytes(b"x")
    with pytest.raises(ValueError, match="must not also be an input"):
        validate_concat_request(ConcatClipsRequest(output=clip, clips=(clip,)))


def test_concat_tab_exposes_native_clip_directory_picker() -> None:
    source = Path("video/gui/tabs.py").read_text(encoding="utf-8")
    concat_tab = source[
        source.index("def render_concat_tab"):source.index("\n\ndef render_test_tab")
    ]

    assert '"Chọn thư mục"' in concat_tab
    assert 'key="concat_select_clips_directory"' in concat_tab
    assert 'kwargs={"state_key": "concat_clips_dir", "directory": True}' in concat_tab
