from __future__ import annotations

import json

import pytest

from audio.pipeline.segment_planner import Segment
from audio.services.tts_cache import TtsCacheSession, build_segment_cache_key


def _segment(text: str = "Xin chào") -> Segment:
    return Segment(text=text, voice="narrator", rate="0%", lang="vi", lang_from_tag=True)


def _key(segment: Segment, *, model: str = "model-a") -> str:
    return build_segment_cache_key(
        segment,
        provider="vieneu",
        voice_map_vi={"narrator": "Doan"},
        voice_map_en={"narrator": "Doan"},
        settings={"model": model, "temperature": 0.7},
    )


def test_cache_key_changes_with_text_voice_rate_or_model() -> None:
    base = _segment()
    assert _key(base) == _key(_segment())
    assert _key(base) != _key(_segment("Nội dung khác"))
    assert _key(base) != _key(base, model="model-b")
    faster = _segment()
    faster.rate = "+10%"
    assert _key(base) != _key(faster)


def test_manifest_resumes_existing_output_and_rejects_tampering(tmp_path) -> None:
    wav_dir = tmp_path / "job"
    cache_dir = tmp_path / "cache"
    key = _key(_segment())
    session = TtsCacheSession(wav_dir=wav_dir, cache_dir=cache_dir, keys=[key])
    output = session.output_path(0)
    output.write_bytes(b"valid-wave-payload")
    session.commit(0)

    resumed = TtsCacheSession(wav_dir=wav_dir, cache_dir=cache_dir, keys=[key]).restore()
    assert resumed.hits == (0,)
    assert resumed.misses == ()

    output.write_bytes(b"tampered")
    restored = TtsCacheSession(wav_dir=wav_dir, cache_dir=cache_dir, keys=[key]).restore()
    assert restored.hits == (0,)
    assert output.read_bytes() == b"valid-wave-payload"


def test_content_cache_materializes_same_segment_in_another_job(tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    key = _key(_segment())
    first = TtsCacheSession(wav_dir=tmp_path / "job-a", cache_dir=cache_dir, keys=[key])
    first.output_path(0).write_bytes(b"shared-audio")
    first.commit(0)

    second = TtsCacheSession(wav_dir=tmp_path / "job-b", cache_dir=cache_dir, keys=[key])
    result = second.restore()

    assert result.hits == (0,)
    assert second.output_path(0).read_bytes() == b"shared-audio"
    manifest = json.loads((tmp_path / "job-b" / ".tts_manifest.json").read_text(encoding="utf-8"))
    assert manifest["segments"]["0"]["key"] == key


def test_cache_miss_unlinks_old_hardlink_without_mutating_cached_audio(tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    old_key = _key(_segment("old"))
    first = TtsCacheSession(wav_dir=tmp_path / "job-a", cache_dir=cache_dir, keys=[old_key])
    first.output_path(0).write_bytes(b"immutable-cache-audio")
    first.commit(0)

    job = TtsCacheSession(wav_dir=tmp_path / "job-b", cache_dir=cache_dir, keys=[old_key])
    assert job.restore().hits == (0,)
    new_key = _key(_segment("new"))
    rerender = TtsCacheSession(wav_dir=tmp_path / "job-b", cache_dir=cache_dir, keys=[new_key])
    assert rerender.restore().misses == (0,)
    rerender.output_path(0).write_bytes(b"new-audio")

    restored_old = TtsCacheSession(wav_dir=tmp_path / "job-c", cache_dir=cache_dir, keys=[old_key])
    assert restored_old.restore().hits == (0,)
    assert restored_old.output_path(0).read_bytes() == b"immutable-cache-audio"


@pytest.mark.parametrize("payload", [
    "null", "[]", "42", '"invalid"',
    '{"schema_version": 1e999, "segments": {}}',
    '{"schema_version": 1, "segments": 42}',
    '{"schema_version": 1, "segments": {"0": 42}}',
])
def test_invalid_manifest_does_not_block_render(tmp_path, payload) -> None:
    wav_dir = tmp_path / "job"
    wav_dir.mkdir()
    (wav_dir / ".tts_manifest.json").write_text(payload, encoding="utf-8")
    session = TtsCacheSession(wav_dir=wav_dir, cache_dir=tmp_path / "cache", keys=[_key(_segment())])
    assert session.restore().misses == (0,)
    session.output_path(0).write_bytes(b"regenerated-audio")
    session.commit(0)
    assert session.restore().hits == (0,)


@pytest.mark.parametrize("location", ["manifest", "cache"])
@pytest.mark.parametrize("bad_value", [None, [], 42, {"size": float("inf")}, {"size": "bad"}])
def test_invalid_cache_entry_is_regenerated(tmp_path, location, bad_value) -> None:
    key = _key(_segment())
    cache_dir = tmp_path / "cache"
    session = TtsCacheSession(wav_dir=tmp_path / "job", cache_dir=cache_dir, keys=[key])
    session.output_path(0).write_bytes(b"original-audio")
    session.commit(0)
    metadata_path = cache_dir / key[:2] / f"{key}.json"
    original = json.loads(metadata_path.read_text(encoding="utf-8"))
    damaged = {**original, **bad_value} if isinstance(bad_value, dict) else bad_value
    if location == "manifest":
        session.manifest_path.write_text(json.dumps({"schema_version": 1, "segments": {"0": damaged}}), encoding="utf-8")
        metadata_path.unlink()
    else:
        metadata_path.write_text(json.dumps(damaged), encoding="utf-8")
        session.manifest_path.unlink()
    restored = TtsCacheSession(wav_dir=session.wav_dir, cache_dir=cache_dir, keys=[key])
    assert restored.restore().misses == (0,)
    restored.output_path(0).write_bytes(b"replacement-audio")
    restored.commit(0)
    assert restored.restore().hits == (0,)
