from __future__ import annotations

import json
import subprocess
from pathlib import Path

from video import media_quality
from video.app_api import VideoQualityGateError
from video.command_builders import build_slideshow_ffmpeg_cmd, build_static_ffmpeg_cmd
from video.encoding_profiles import resolve_encoding_profile


def test_quality_command_timeout_is_configurable_and_actionable(monkeypatch) -> None:
    monkeypatch.setattr(media_quality.config, "QUALITY_CHECK_TIMEOUT_SECONDS", 0.25)

    def time_out(_cmd, **kwargs):
        assert kwargs["timeout"] == 0.25
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=kwargs["timeout"])

    monkeypatch.setattr(media_quality.subprocess, "run", time_out)

    try:
        media_quality._run_quality_command(["ffprobe"], step="media probe")
    except RuntimeError as exc:
        assert "media probe" in str(exc)
        assert "0.25 seconds" in str(exc)
    else:
        raise AssertionError("Expected a quality-check timeout error")


def test_slideshow_filter_can_be_passed_by_script_to_avoid_windows_command_limit() -> None:
    command = build_slideshow_ffmpeg_cmd(
        ffmpeg_base=["ffmpeg"],
        concat_list=Path("slides.ffconcat"),
        audio=Path("audio.wav"),
        output=Path("video.mp4"),
        vf_filter="a" * 40_000,
        vf_filter_script=Path("video.fffilter"),
        video_codec="libx264",
        preset="medium",
        crf=18,
        tune="stillimage",
        audio_codec="aac",
        audio_bitrate="192k",
        movflags="+faststart",
    )

    assert command[command.index("-filter_script:v") + 1] == "video.fffilter"
    assert "-vf" not in command
    assert "a" * 40_000 not in command
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


def test_subtitle_preparation_leaves_default_wrapping_to_libass(tmp_path: Path) -> None:
    source = tmp_path / "story.srt"
    output = tmp_path / "prepared.srt"
    subtitle = (
        "Nhưng ILO nhấn mạnh rằng con người vẫn cần thiết trong nhiều nhiệm vụ, "
        "nên kết quả có khả năng là tái cấu trúc vai trò hơn là xóa bỏ nguyên nghề."
    )
    source.write_text(
        f"1\n00:00:00,000 --> 00:00:06,000\n{subtitle}\n",
        encoding="utf-8",
    )

    prepared, changed = media_quality.prepare_subtitle_for_video(source, output)

    assert prepared == output
    assert changed is True
    assert output.read_text(encoding="utf-8").splitlines()[2] == subtitle


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


def test_video_quality_report_fails_when_visual_ssim_cannot_be_measured(
    monkeypatch, tmp_path: Path
) -> None:
    video = tmp_path / "story.mp4"
    video.write_bytes(b"ftyp" + b"moov" + b"mdat")
    monkeypatch.setattr(
        media_quality,
        "probe_media",
        lambda *_args, **_kwargs: {
            "format": {"duration": "10.0", "start_time": "0.0"},
            "streams": [
                {
                    "codec_type": "video", "codec_name": "h264", "width": 1920,
                    "height": 1080, "sample_aspect_ratio": "1:1",
                    "avg_frame_rate": "24/1", "pix_fmt": "yuv420p", "duration": "10.0",
                    "color_primaries": "bt709", "color_transfer": "bt709",
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
            "input_i": -16.0, "input_tp": -1.8, "input_lra": 7.0,
            "input_thresh": -26.0, "target_offset": 0.0,
        },
    )
    monkeypatch.setattr(media_quality, "_decode_check", lambda *_args, **_kwargs: (True, "", []))
    monkeypatch.setattr(
        media_quality,
        "sample_visual_ssim",
        lambda *_args, **_kwargs: [
            {"ssim": None, "return_code": 1, "error": "ffmpeg sampling failed"}
        ],
    )

    _, report = media_quality.write_video_quality_report(
        video,
        ffmpeg_exe="ffmpeg",
        ffprobe_exe="ffprobe",
        loudness_profile="narration",
        expected_width=1920,
        expected_height=1080,
        expected_fps=24,
    )

    assert report["checks"]["visual_ssim"] is False
    assert report["passed"] is False
    assert report["visual_samples"][0]["error"] == "ffmpeg sampling failed"


def test_quality_gate_error_preserves_created_artifact_paths(tmp_path: Path) -> None:
    error = VideoQualityGateError(
        failed_checks=["visual_ssim"],
        report_path=tmp_path / "story.video_quality.json",
        output_path=tmp_path / "story.mp4",
        result_manifest_path=tmp_path / "story.result.json",
    )

    assert error.failed_checks == ("visual_ssim",)
    assert error.output_path.name == "story.mp4"
    assert error.report_path.name == "story.video_quality.json"
    assert "visual_ssim" in str(error)
