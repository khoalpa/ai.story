from __future__ import annotations

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

