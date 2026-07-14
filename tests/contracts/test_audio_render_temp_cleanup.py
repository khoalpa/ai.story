from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio.adapters import ffmpeg_audio_mixer as mixer
from audio.pipeline.segment_planner import Segment


def _make_mix_config() -> mixer.FfmpegMixConfig:
    return mixer.FfmpegMixConfig(ffmpeg_exe="ffmpeg", ffprobe_exe="ffprobe")


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


def test_final_output_filter_increases_volume_for_plain_output() -> None:
    filter_chain = mixer.build_final_output_filter_chain(mixer.POST_FX_PRESET_NONE)

    assert filter_chain == "volume=3.0dB,alimiter=limit=0.97"


def test_final_output_filter_keeps_storytelling_fx_and_adds_output_gain() -> None:
    filter_chain = mixer.build_final_output_filter_chain(mixer.POST_FX_PRESET_STORYTELLING_VI)

    assert filter_chain is not None
    assert filter_chain.startswith("afftdn=nr=8:nf=-32:tn=1")
    assert filter_chain.endswith("volume=3.0dB,alimiter=limit=0.97")


def test_apply_post_fx_uses_final_output_gain_filter(monkeypatch, tmp_path: Path) -> None:
    input_wav = tmp_path / "input.wav"
    output_file = tmp_path / "story.mp3"
    captured_cmds: list[list[str]] = []
    input_wav.write_bytes(b"wav")

    def fake_run_ffmpeg_with_progress(cmd, *_args, **_kwargs):  # noqa: ANN001
        captured_cmds.append(cmd)
        Path(cmd[-1]).write_bytes(b"louder")

    monkeypatch.setattr(mixer, "get_audio_duration_seconds", lambda *_args, **_kwargs: 1.0)
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
    assert captured_cmds[0][captured_cmds[0].index("-af") + 1] == "volume=3.0dB,alimiter=limit=0.97"

