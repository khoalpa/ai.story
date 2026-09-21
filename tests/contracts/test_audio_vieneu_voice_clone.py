from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from audio.adapters import tts_core
from audio.services import vieneu_voice_clone
from audio.vieneu_voice_store import (
    delete_cloned_voice,
    get_cloned_voice,
    list_cloned_voices,
    load_cloned_voice_payload,
    save_cloned_voice,
)


def _write_wav(path: Path, *, seconds: float = 1.0, sample_rate: int = 44100) -> None:
    frames = b"\x00\x00" * int(seconds * sample_rate)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


def test_cloned_voice_store_round_trip_and_delete(tmp_path: Path) -> None:
    reference = tmp_path / "reference.wav"
    _write_wav(reference)
    voice = save_cloned_voice(
        name="Giọng thử",
        speaker_embedding=np.asarray([0.1, 0.2], dtype=np.float32),
        reference_codes=np.asarray([1, 2, 3], dtype=np.int64),
        consent_confirmed=True,
        reference_audio=reference,
        keep_reference_audio=True,
        root=tmp_path / "voices",
    )

    assert voice.selection_id.startswith("clone:")
    assert get_cloned_voice(voice.selection_id, root=tmp_path / "voices") == voice
    assert list_cloned_voices(root=tmp_path / "voices") == (voice,)
    payload = load_cloned_voice_payload(voice.selection_id, root=tmp_path / "voices")
    assert payload["speaker_emb"].tolist() == pytest.approx([0.1, 0.2])
    assert payload["codes"].tolist() == [1, 2, 3]
    assert (tmp_path / "voices" / voice.id / "reference.wav").is_file()

    assert delete_cloned_voice(voice.selection_id, root=tmp_path / "voices") == voice
    assert list_cloned_voices(root=tmp_path / "voices") == tuple()


def test_cloned_voice_requires_consent_and_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="xác nhận"):
        save_cloned_voice(
            name="Không hợp lệ",
            speaker_embedding=[0.1],
            reference_codes=[1],
            consent_confirmed=False,
            root=tmp_path,
        )
    with pytest.raises(ValueError, match="Invalid cloned voice id"):
        get_cloned_voice("clone:../../outside", root=tmp_path)


def test_corrupt_manifest_is_not_listed(tmp_path: Path) -> None:
    voice_dir = tmp_path / "12345678-1234-4234-8234-123456789abc"
    voice_dir.mkdir()
    (voice_dir / "manifest.json").write_text("{broken", encoding="utf-8")
    assert list_cloned_voices(root=tmp_path) == tuple()


def test_vieneu_resolver_loads_clone_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {"speaker_emb": np.asarray([0.5]), "codes": np.asarray([7])}
    monkeypatch.setattr(tts_core, "load_cloned_voice_payload", lambda *_args, **_kwargs: expected)
    segment = SimpleNamespace(lang="vi", voice="narrator")

    voice_id, payload = tts_core.resolve_vieneu_segment_voice(
        object(),
        segment,
        {"narrator": "clone:12345678-1234-4234-8234-123456789abc"},
        {},
        vieneu_mode="v3turbo",
    )

    assert voice_id.startswith("clone:")
    assert payload is expected


def test_vieneu_resolver_rejects_clone_outside_v3() -> None:
    segment = SimpleNamespace(lang="vi", voice="narrator")
    with pytest.raises(Exception, match="v3 Turbo"):
        tts_core.resolve_vieneu_segment_voice(
            object(),
            segment,
            {"narrator": "clone:12345678-1234-4234-8234-123456789abc"},
            {},
            vieneu_mode="standard",
        )


def test_runtime_preset_catalog_does_not_invent_fallback_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tts_core, "_list_vieneu_preset_voices_cached", lambda **_kwargs: tuple())
    assert tts_core.list_vieneu_preset_voices(mode="v3turbo") == tuple()


def test_runtime_preset_catalog_returns_empty_when_engine_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(**_kwargs):
        raise RuntimeError("engine unavailable")

    monkeypatch.setattr(tts_core, "_list_vieneu_preset_voices_cached", fail)
    assert tts_core.list_vieneu_preset_voices(mode="v3turbo") == tuple()


def test_create_clone_normalizes_enrolls_and_does_not_keep_audio_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    _write_wav(source, seconds=4)
    engine = SimpleNamespace(encode_reference=lambda _path: (np.asarray([0.2]), np.asarray([4, 5])))
    monkeypatch.setattr(vieneu_voice_clone, "get_vieneu_engine", lambda **_kwargs: engine)
    monkeypatch.setattr(vieneu_voice_clone, "resolve_vieneu_model_for_runtime", lambda *_args, **_kwargs: "model-v3")
    def fake_normalize(input_path: Path, destination: Path, **_kwargs) -> Path:
        destination.write_bytes(input_path.read_bytes())
        return destination

    monkeypatch.setattr(vieneu_voice_clone, "normalize_reference_audio", fake_normalize)
    captured: dict[str, object] = {}

    def fake_save(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(name=kwargs["name"])

    monkeypatch.setattr(vieneu_voice_clone, "save_cloned_voice", fake_save)

    voice, quality = vieneu_voice_clone.create_cloned_voice(
        reference_audio=source,
        name="MVP",
        consent_confirmed=True,
        keep_reference_audio=False,
    )

    assert voice.name == "MVP"
    assert quality.duration_seconds == pytest.approx(4.0)
    assert captured["model_family"] == "v3turbo"
    assert captured["model_fingerprint"] == "model-v3"
    assert captured["keep_reference_audio"] is False
