from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from audio.model_store import provider_cache_dir
from audio.pipeline.segment_planner import Segment

CACHE_SCHEMA_VERSION = 1
MANIFEST_NAME = ".tts_manifest.json"


def _metadata_int(value: object) -> int:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_segment_cache_key(
    segment: Segment,
    *,
    provider: str,
    voice_map_vi: Mapping[str, str],
    voice_map_en: Mapping[str, str],
    settings: Mapping[str, Any],
) -> str:
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "provider": str(provider),
        "text": unicodedata.normalize("NFC", str(getattr(segment, "text", "") or "").strip()),
        "voice": str(getattr(segment, "voice", "narrator")),
        "rate": str(getattr(segment, "rate", "0%") or "0%"),
        "lang": str(getattr(segment, "lang", "vi") or "vi"),
        "lang_from_tag": bool(getattr(segment, "lang_from_tag", False)),
        "voice_map_vi": dict(voice_map_vi),
        "voice_map_en": dict(voice_map_en),
        "settings": dict(settings),
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


@dataclass(frozen=True)
class CacheRestoreResult:
    hits: tuple[int, ...]
    misses: tuple[int, ...]


class TtsCacheSession:
    def __init__(self, *, wav_dir: Path, cache_dir: Path | None, keys: list[str], enabled: bool = True) -> None:
        self.wav_dir = Path(wav_dir)
        configured_cache = str(os.environ.get("AUDIO_TTS_CACHE_DIR") or "").strip()
        self.cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path(configured_cache)
            if configured_cache
            else provider_cache_dir("audio", __file__) / "tts_segments"
        )
        self.keys = list(keys)
        self.enabled = bool(enabled)
        self.manifest_path = self.wav_dir / MANIFEST_NAME
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, object]] = {}
        self.wav_dir.mkdir(parents=True, exist_ok=True)
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_manifest()

    def output_path(self, index: int) -> Path:
        return self.wav_dir / f"seg_{index:03d}.wav"

    def _cache_paths(self, key: str) -> tuple[Path, Path]:
        directory = self.cache_dir / key[:2]
        return directory / f"{key}.wav", directory / f"{key}.json"

    def _load_manifest(self) -> None:
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or _metadata_int(raw.get("schema_version")) != CACHE_SCHEMA_VERSION:
                return
            segments = raw.get("segments")
            if isinstance(segments, dict):
                self._entries = {
                    key: entry for key, entry in segments.items() if isinstance(entry, dict)
                }
        except (OSError, ValueError, TypeError):
            self._entries = {}

    def _valid_file(self, path: Path, expected_sha256: str | None = None, expected_size: int | None = None) -> bool:
        try:
            if not path.is_file() or path.stat().st_size <= 0:
                return False
            if expected_size is not None and path.stat().st_size != expected_size:
                return False
            return expected_sha256 is None or _sha256_file(path) == expected_sha256
        except OSError:
            return False

    def _read_cache_metadata(self, key: str) -> tuple[Path, dict[str, object]] | None:
        cache_wav, metadata_path = self._cache_paths(key)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                return None
            sha256 = str(metadata.get("sha256") or "")
            size = _metadata_int(metadata.get("size"))
        except (OSError, ValueError, TypeError):
            return None
        if metadata.get("key") != key or not sha256 or not self._valid_file(cache_wav, sha256, size):
            return None
        return cache_wav, metadata

    @staticmethod
    def _materialize(source: Path, target: Path) -> None:
        temporary = target.with_name(f".{target.name}.cache-tmp")
        temporary.unlink(missing_ok=True)
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copy2(source, temporary)
        os.replace(temporary, target)

    def restore(self) -> CacheRestoreResult:
        if not self.enabled:
            for index in range(len(self.keys)):
                self.output_path(index).unlink(missing_ok=True)
            return CacheRestoreResult((), tuple(range(len(self.keys))))
        hits: list[int] = []
        misses: list[int] = []
        for index, key in enumerate(self.keys):
            output = self.output_path(index)
            entry = dict(self._entries.get(str(index)) or {})
            expected_sha = str(entry.get("sha256") or "")
            expected_size = _metadata_int(entry.get("size"))
            if entry.get("key") == key and expected_sha and self._valid_file(output, expected_sha, expected_size):
                hits.append(index)
                continue
            cached = self._read_cache_metadata(key)
            if cached is None:
                # A previous cache hit may have materialized this path as a
                # hard-link. Unlink before TTS writes so the cache stays immutable.
                output.unlink(missing_ok=True)
                misses.append(index)
                continue
            cache_wav, metadata = cached
            self._materialize(cache_wav, output)
            self._entries[str(index)] = {"key": key, "sha256": metadata["sha256"], "size": metadata["size"]}
            hits.append(index)
        self._write_manifest()
        return CacheRestoreResult(tuple(hits), tuple(misses))

    def commit(self, index: int) -> None:
        if not self.enabled:
            return
        output = self.output_path(index)
        if not self._valid_file(output):
            return
        key = self.keys[index]
        sha256 = _sha256_file(output)
        size = output.stat().st_size
        cache_wav, metadata_path = self._cache_paths(key)
        with self._lock:
            cache_wav.parent.mkdir(parents=True, exist_ok=True)
            if not self._valid_file(cache_wav, sha256, size):
                temporary = cache_wav.with_name(f".{cache_wav.name}.{os.getpid()}.tmp")
                shutil.copy2(output, temporary)
                os.replace(temporary, cache_wav)
            metadata = {"schema_version": CACHE_SCHEMA_VERSION, "key": key, "sha256": sha256, "size": size}
            metadata_tmp = metadata_path.with_name(f".{metadata_path.name}.{os.getpid()}.tmp")
            metadata_tmp.write_bytes(_canonical_json(metadata))
            os.replace(metadata_tmp, metadata_path)
            self._entries[str(index)] = {"key": key, "sha256": sha256, "size": size}
            self._write_manifest()

    def _write_manifest(self) -> None:
        if not self.enabled:
            return
        payload = {"schema_version": CACHE_SCHEMA_VERSION, "segments": self._entries}
        temporary = self.manifest_path.with_name(f".{self.manifest_path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(_canonical_json(payload))
        os.replace(temporary, self.manifest_path)
