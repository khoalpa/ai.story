from __future__ import annotations

import asyncio
import wave

import pytest

from audio.exceptions import TtsError
from audio.pipeline.segment_planner import Segment
from audio.services import tts_render


def _segment(text: str, *, pause_ms: int = 0) -> Segment:
    return Segment(
        text=text,
        voice="narrator",
        rate="0%",
        lang="vi",
        lang_from_tag=True,
        pause_ms_before=pause_ms,
    )


def _config(tmp_path, *, batch: bool) -> tts_render.TtsRenderConfig:  # noqa: ANN001
    return tts_render.TtsRenderConfig(
        wav_dir=tmp_path,
        voice_map_vi={"narrator": "narrator"},
        voice_map_en={"narrator": "narrator"},
        abbr_map={},
        tts_provider="vieneu",
        vieneu_mode="standard" if batch else "turbo",
        vieneu_model_name="model",
        vieneu_device="cpu",
        vieneu_render_use_batch=batch,
        cache_enabled=False,
    )


@pytest.mark.parametrize("batch", [False, True])
def test_vieneu_renders_silence_without_calling_engine(monkeypatch, tmp_path, batch: bool) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        tts_render,
        "get_vieneu_engine",
        lambda **_kwargs: pytest.fail("VieNeu engine must not load for silence-only input"),
    )
    progress: list[tuple[int, int]] = []

    asyncio.run(
        tts_render.render_tts_segments_async(
            [_segment("", pause_ms=750)],
            _config(tmp_path, batch=batch),
            progress_callback=lambda completed, total: progress.append((completed, total)),
        )
    )

    output = tmp_path / "seg_000.wav"
    with wave.open(str(output), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 24_000
        assert audio.getnframes() == 18_000
        assert audio.readframes(audio.getnframes()).strip(b"\x00") == b""
    assert progress[-1] == (1, 1)


def test_vieneu_batch_excludes_silence_and_keeps_progress_monotonic(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    calls: list[list[str]] = []

    class FakeEngine:
        def get_preset_voice(self, voice_id: str) -> dict[str, str]:
            return {"voice_id": voice_id}

        def list_preset_voices(self) -> list[tuple[str, str]]:
            return [("Narrator", "narrator")]

        def infer_batch(self, texts, **_kwargs):  # noqa: ANN001, ANN003
            calls.append(list(texts))
            return [f"audio:{text}" for text in texts]

        def save(self, audio, out_wav):  # noqa: ANN001
            out_wav.write_text(str(audio), encoding="utf-8")

    monkeypatch.setattr(tts_render, "get_vieneu_engine", lambda **_kwargs: FakeEngine())
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_for_runtime", lambda value, *_args, **_kwargs: str(value))
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_name", lambda value, _mode: str(value))
    progress: list[tuple[int, int]] = []

    asyncio.run(
        tts_render.render_tts_segments_async(
            [_segment("Một"), _segment("", pause_ms=500), _segment("Hai")],
            _config(tmp_path, batch=True),
            progress_callback=lambda completed, total: progress.append((completed, total)),
        )
    )

    assert calls == [["Một", "Hai"]]
    assert [completed for completed, _total in progress] == sorted(completed for completed, _total in progress)
    assert progress[-1] == (3, 3)


def test_vieneu_rejects_empty_segment_without_pause(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        tts_render,
        "get_vieneu_engine",
        lambda **_kwargs: pytest.fail("invalid input must fail before engine initialization"),
    )

    with pytest.raises(TtsError, match="Segment 0 rỗng và không có thời lượng pause"):
        asyncio.run(tts_render.render_tts_segments_async([_segment("")], _config(tmp_path, batch=False)))
