from __future__ import annotations

import json
from pathlib import Path

from video import media_quality
from video.command_builders import build_static_ffmpeg_cmd
from video.encoding_profiles import resolve_encoding_profile


def test_encoding_profiles_select_platform_resolution_and_quality() -> None:
    youtube = resolve_encoding_profile("auto", "16x9")
    tiktok = resolve_encoding_profile("auto", "9x16")
    master = resolve_encoding_profile("master", "16x9")
    hevc = resolve_encoding_profile("master_hevc", "16x9")

    assert (youtube.width, youtube.height, youtube.fps, youtube.crf) == (3840, 2160, 24, 19)
    assert (tiktok.width, tiktok.height, tiktok.fps) == (1080, 1920, 30)
    assert master.crf == 17
    assert (hevc.video_codec, hevc.pixel_format) == ("libx265", "yuv420p10le")


def test_static_command_uses_cfr_color_gop_and_audio_delivery_settings(tmp_path: Path) -> None:
    command = build_static_ffmpeg_cmd(
        ffmpeg_base=["ffmpeg"],
        cover=tmp_path / "cover.png",
        audio=tmp_path / "audio.wav",
        output=tmp_path / "video.mp4",
        vf_filter="scale=1920:1080",
        video_codec="libx264",
        preset="slow",
        crf=19,
        tune="stillimage",
        fps=24,
        audio_codec="aac",
        audio_bitrate="192k",
        movflags="+faststart",
    )

    assert command[command.index("-fps_mode") + 1] == "cfr"
    assert command[command.index("-g") + 1] == "48"
    assert command[command.index("-color_trc") + 1] == "bt709"
    assert command[command.index("-ar") + 1] == "48000"
    assert command[command.index("-ac") + 1] == "2"
    assert command[command.index("-movflags") + 1] == "+faststart"


def test_subtitle_preparation_wraps_long_lines_without_changing_timestamps(tmp_path: Path) -> None:
    source = tmp_path / "story.srt"
    output = tmp_path / "wrapped.srt"
    source.write_text(
        "1\n00:00:00,000 --> 00:00:04,000\n"
        "This is a deliberately long subtitle line that needs wrapping inside the platform safe area.\n",
        encoding="utf-8",
    )

    prepared, changed = media_quality.prepare_subtitle_for_video(source, output, max_chars=40)

    assert prepared == output
    assert changed is True
    rendered = output.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:04,000" in rendered
    assert all(len(line) <= 40 for line in rendered.splitlines() if line and "-->" not in line and not line.isdigit())


def test_video_quality_report_gates_delivery_contract(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "story.mp4"
    video.write_bytes(b"ftyp" + b"moov" + b"mdat")
    monkeypatch.setattr(
        media_quality,
        "probe_media",
        lambda *_args, **_kwargs: {
            "format": {"duration": "10.0", "start_time": "0.0"},
            "streams": [
                {
                    "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                    "sample_aspect_ratio": "1:1", "avg_frame_rate": "24/1", "pix_fmt": "yuv420p",
                    "duration": "10.0", "color_primaries": "bt709", "color_transfer": "bt709",
                    "color_space": "bt709", "color_range": "tv",
                },
                {
                    "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000",
                    "channels": 2, "duration": "10.0",
                },
            ],
        },
    )
    monkeypatch.setattr(
        media_quality,
        "analyze_loudness",
        lambda *_args, **_kwargs: {
            "input_i": -16.1, "input_tp": -1.8, "input_lra": 7.0,
            "input_thresh": -26.0, "target_offset": 0.0,
        },
    )
    monkeypatch.setattr(media_quality, "_decode_check", lambda *_args, **_kwargs: (True, "", []))
    monkeypatch.setattr(media_quality, "sample_visual_ssim", lambda *_args, **_kwargs: [{"ssim": 0.98}])

    report_path, report = media_quality.write_video_quality_report(
        video,
        ffmpeg_exe="ffmpeg",
        ffprobe_exe="ffprobe",
        loudness_profile="narration",
        expected_width=1920,
        expected_height=1080,
        expected_fps=24,
    )

    assert report["passed"] is True
    assert all(report["checks"].values())
    assert json.loads(report_path.read_text(encoding="utf-8"))["measured"]["integrated_lufs"] == -16.1
