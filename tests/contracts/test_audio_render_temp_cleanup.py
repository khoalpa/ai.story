from __future__ import annotations

import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio.adapters import ffmpeg_audio_mixer as mixer
from audio.pipeline.segment_planner import Segment


def _make_mix_config() -> mixer.FfmpegMixConfig:
    return mixer.FfmpegMixConfig(ffmpeg_exe="ffmpeg", ffprobe_exe="ffprobe", quality_gate=False)


def _make_segment() -> Segment:
    return Segment(text="hello", voice="narrator", rate="+0%")


def _prepare_wav_dir(out_file: Path) -> None:
    wav_dir = out_file.parent / f"{out_file.stem}_wav"
    wav_dir.mkdir(parents=True)
    (wav_dir / "seg_000.wav").write_bytes(b"voice")


def _write_pcm_wav(path: Path, *, seconds: float, sample_rate: int = 8000) -> None:
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frames)


def test_ffmpeg_mix_audio_removes_temp_dir_after_success(monkeypatch, tmp_path: Path) -> None:
    out_file = tmp_path / "story.wav"
    _prepare_wav_dir(out_file)

    def fake_run(cmd, **_kwargs):  # noqa: ANN001
        Path(cmd[-1]).write_bytes(b"audio")
        return SimpleNamespace(returncode=0, stdout="", stderr=b"")

    def fake_run_ffmpeg_with_progress(cmd, *_args, **_kwargs):  # noqa: ANN001
        Path(cmd[-1]).write_bytes(b"assembled")

    def fake_apply_post_fx(input_wav: Path, output_file: Path, **_kwargs) -> Path:
        assert input_wav.exists()
        output_file.write_bytes(b"final")
        return output_file

    monkeypatch.setattr(mixer.subprocess, "run", fake_run)
    monkeypatch.setattr(mixer, "get_audio_duration_seconds", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(mixer, "run_ffmpeg_with_progress", fake_run_ffmpeg_with_progress)
    monkeypatch.setattr(mixer, "apply_post_fx", fake_apply_post_fx)

    timeline, final_out = mixer.ffmpeg_mix_audio(
        [_make_segment()],
        out_file,
        bgm_dir=tmp_path,
        mix_config=_make_mix_config(),
    )

    assert timeline == [{"idx": 0, "text": "hello", "start": 0.0, "end": 1.0}]
    assert final_out == out_file
    assert out_file.read_bytes() == b"final"
    assert not (tmp_path / "story_mix_tmp").exists()


def test_ffmpeg_mix_audio_removes_temp_dir_after_failure(monkeypatch, tmp_path: Path) -> None:
    out_file = tmp_path / "story.wav"
    _prepare_wav_dir(out_file)

    def fake_run(cmd, **_kwargs):  # noqa: ANN001
        Path(cmd[-1]).write_bytes(b"audio")
        return SimpleNamespace(returncode=0, stdout="", stderr=b"")

    def fake_run_ffmpeg_with_progress(*_args, **_kwargs):  # noqa: ANN001
        raise RuntimeError("assemble failed")

    monkeypatch.setattr(mixer.subprocess, "run", fake_run)
    monkeypatch.setattr(mixer, "get_audio_duration_seconds", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(mixer, "run_ffmpeg_with_progress", fake_run_ffmpeg_with_progress)

    with pytest.raises(RuntimeError, match="assemble failed"):
        mixer.ffmpeg_mix_audio(
            [_make_segment()],
            out_file,
            bgm_dir=tmp_path,
            mix_config=_make_mix_config(),
        )

    assert not (tmp_path / "story_mix_tmp").exists()


def test_get_audio_duration_seconds_falls_back_to_wave_when_ffprobe_fails(
    monkeypatch, tmp_path: Path
) -> None:
    wav_path = tmp_path / "segment.wav"
    _write_pcm_wav(wav_path, seconds=1.25)

    def fake_run(*_args, **_kwargs):  # noqa: ANN001
        return SimpleNamespace(returncode=1, stdout="", stderr=b"ffprobe unavailable")

    monkeypatch.setattr(mixer.subprocess, "run", fake_run)

    assert mixer.get_audio_duration_seconds(wav_path, "missing-ffprobe") == 1.25


def test_plain_output_has_no_tone_filter_before_loudness_normalization() -> None:
    filter_chain = mixer.build_final_output_filter_chain(mixer.POST_FX_PRESET_NONE)

    assert filter_chain is None


def test_storytelling_fx_is_lightweight_and_has_no_denoise_or_reverb() -> None:
    filter_chain = mixer.build_final_output_filter_chain(mixer.POST_FX_PRESET_STORYTELLING_VI)

    assert filter_chain is not None
    assert filter_chain.startswith("highpass=f=75")
    assert "acompressor=" in filter_chain
    assert "afftdn=" not in filter_chain
    assert "aecho=" not in filter_chain


def test_apply_post_fx_uses_measured_two_pass_loudness_filter(monkeypatch, tmp_path: Path) -> None:
    input_wav = tmp_path / "input.wav"
    output_file = tmp_path / "story.mp3"
    captured_cmds: list[list[str]] = []
    input_wav.write_bytes(b"wav")

    def fake_run_ffmpeg_with_progress(cmd, *_args, **_kwargs):  # noqa: ANN001
        captured_cmds.append(cmd)
        Path(cmd[-1]).write_bytes(b"louder")

    monkeypatch.setattr(mixer, "get_audio_duration_seconds", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(
        mixer,
        "analyze_loudness",
        lambda *_args, **_kwargs: {
            "input_i": -24.0,
            "input_tp": -8.0,
            "input_lra": 4.0,
            "input_thresh": -34.0,
            "target_offset": 0.1,
        },
    )
    monkeypatch.setattr(mixer, "run_ffmpeg_with_progress", fake_run_ffmpeg_with_progress)

    final_out = mixer.apply_post_fx(
        input_wav=input_wav,
        output_file=output_file,
        ffmpeg_exe="ffmpeg",
        ffprobe_exe="ffprobe",
        preset=mixer.POST_FX_PRESET_NONE,
        audio_format="mp3",
    )

    assert final_out == output_file
    assert output_file.read_bytes() == b"louder"
    assert captured_cmds
    final_filter = captured_cmds[0][captured_cmds[0].index("-af") + 1]
    assert final_filter.startswith("loudnorm=I=-16.0:LRA=9.0:TP=-1.5")
    assert "measured_I=-24.0" in final_filter
    assert "linear=true" in final_filter
    assert "-b:a" in captured_cmds[0]
    assert captured_cmds[0][captured_cmds[0].index("-b:a") + 1] == "192k"


def test_loudness_profiles_have_expected_delivery_targets() -> None:
    assert mixer.get_loudness_target("narration") == mixer.LoudnessTarget(-16.0, -1.5, 9.0)
    assert mixer.get_loudness_target("social_video") == mixer.LoudnessTarget(-14.0, -1.0, 9.0)
    assert mixer.get_loudness_target("broadcast") == mixer.LoudnessTarget(-23.0, -2.0, 7.0)


def test_output_codecs_use_24_bit_wav_and_predictable_mp3_bitrate() -> None:
    assert mixer.get_output_codec_args("wav") == ["-acodec", "pcm_s24le"]
    assert mixer.get_output_codec_args("mp3", 256) == [
        "-acodec", "libmp3lame", "-b:a", "256k", "-write_xing", "1",
    ]


def test_quality_report_records_and_gates_export_measurements(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "story.wav"
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(
        mixer,
        "analyze_loudness",
        lambda *_args, **_kwargs: {
            "input_i": -16.2,
            "input_tp": -1.7,
            "input_lra": 6.5,
            "input_thresh": -26.0,
            "target_offset": 0.0,
        },
    )
    monkeypatch.setattr(
        mixer,
        "probe_audio_stream",
        lambda *_args, **_kwargs: {
            "streams": [{"sample_rate": "48000", "channels": 2, "codec_name": "pcm_s24le"}],
        },
    )
    monkeypatch.setattr(mixer, "get_audio_duration_seconds", lambda *_args, **_kwargs: 10.02)

    report_path, report = mixer.write_audio_quality_report(
        audio_path,
        source_duration_seconds=10.0,
        ffmpeg_exe="ffmpeg",
        ffprobe_exe="ffprobe",
        loudness_profile="narration",
        expected_sample_rate=48000,
        expected_channels=2,
    )

    assert report["passed"] is True
    assert all(report["checks"].values())
    assert json.loads(report_path.read_text(encoding="utf-8"))["measured"]["integrated_lufs"] == -16.2


def test_quality_report_allows_subaudible_segment_loudness_margin(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "story.wav"
    audio_path.write_bytes(b"audio")
    segment_files = [tmp_path / f"seg_{index:03d}.wav" for index in range(3)]
    for segment_file in segment_files:
        segment_file.write_bytes(b"audio")

    segment_loudness = {
        "seg_000": -19.5,
        "seg_001": -19.5,
        # A 3.25 LU drop should not fail because FFmpeg's short-clip measurement
        # and normal TTS delivery variation can exceed 3 LU by a small fraction.
        "seg_002": -22.75,
    }

    def fake_analyze_loudness(path, *_args, **_kwargs):  # noqa: ANN001, ANN202
        input_i = segment_loudness.get(path.stem, -16.0)
        return {
            "input_i": input_i,
            "input_tp": -1.7,
            "input_lra": 6.5,
            "input_thresh": -26.0,
            "target_offset": 0.0,
        }

    monkeypatch.setattr(mixer, "analyze_loudness", fake_analyze_loudness)
    monkeypatch.setattr(
        mixer,
        "probe_audio_stream",
        lambda *_args, **_kwargs: {
            "streams": [{"sample_rate": "48000", "channels": 2, "codec_name": "pcm_s24le"}],
        },
    )
    monkeypatch.setattr(mixer, "get_audio_duration_seconds", lambda *_args, **_kwargs: 10.0)

    _report_path, report = mixer.write_audio_quality_report(
        audio_path,
        source_duration_seconds=10.0,
        ffmpeg_exe="ffmpeg",
        ffprobe_exe="ffprobe",
        loudness_profile="narration",
        expected_sample_rate=48000,
        expected_channels=2,
        segment_files=segment_files,
    )

    assert report["segments"]["maximum_drop_from_median_lu"] == 3.5
    assert report["segments"]["quiet_segments"] == []
    assert report["checks"]["segment_loudness_consistency"] is True

