from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audio.model_store import models_root

CLONED_VOICE_PREFIX = "clone:"
VOICE_MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class ClonedVoice:
    schema_version: int
    id: str
    name: str
    provider: str
    model_family: str
    model_fingerprint: str
    language: str
    description: str
    gender: str
    speaker_embedding_file: str
    reference_codes_file: str | None
    reference_audio_file: str | None
    consent_confirmed: bool
    created_at: str

    @property
    def selection_id(self) -> str:
        return f"{CLONED_VOICE_PREFIX}{self.id}"


def cloned_voices_root(module_file: str | Path | None = None) -> Path:
    configured = str(os.environ.get("AI_AUDIO_VOICES_ROOT") or "").strip()
    root = (
        Path(configured).expanduser().resolve()
        if configured
        else (models_root(module_file or __file__) / "vieneu_custom_voices").resolve()
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_cloned_voice_id(value: object) -> bool:
    return str(value or "").strip().lower().startswith(CLONED_VOICE_PREFIX)


def _voice_uuid(selection_or_id: object) -> str:
    raw = str(selection_or_id or "").strip()
    if raw.lower().startswith(CLONED_VOICE_PREFIX):
        raw = raw[len(CLONED_VOICE_PREFIX):]
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid cloned voice id: {selection_or_id!r}") from exc


def _voice_dir(selection_or_id: object, *, root: Path | None = None) -> Path:
    store_root = (root or cloned_voices_root()).resolve()
    target = (store_root / _voice_uuid(selection_or_id)).resolve()
    try:
        target.relative_to(store_root)
    except ValueError as exc:  # defensive; UUID validation should already prevent this
        raise ValueError("Cloned voice path must stay inside the voice store") from exc
    return target


def _read_manifest(path: Path) -> ClonedVoice:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ClonedVoice(**payload)


def list_cloned_voices(*, root: Path | None = None) -> tuple[ClonedVoice, ...]:
    store_root = (root or cloned_voices_root()).resolve()
    if not store_root.exists():
        return tuple()
    voices: list[ClonedVoice] = []
    for manifest in sorted(store_root.glob(f"*/{VOICE_MANIFEST_NAME}")):
        try:
            voice = _read_manifest(manifest)
            _voice_uuid(voice.id)
            voices.append(voice)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return tuple(sorted(voices, key=lambda item: (item.name.casefold(), item.id)))


def get_cloned_voice(selection_or_id: object, *, root: Path | None = None) -> ClonedVoice:
    manifest = _voice_dir(selection_or_id, root=root) / VOICE_MANIFEST_NAME
    if not manifest.is_file():
        raise FileNotFoundError(f"Cloned voice not found: {selection_or_id}")
    voice = _read_manifest(manifest)
    if voice.id != _voice_uuid(selection_or_id):
        raise ValueError("Cloned voice manifest id does not match its directory")
    return voice


def save_cloned_voice(
    *,
    name: str,
    speaker_embedding: Any,
    reference_codes: Any | None,
    language: str = "vi",
    description: str = "",
    gender: str = "",
    model_family: str = "v3turbo",
    model_fingerprint: str = "",
    consent_confirmed: bool,
    reference_audio: Path | None = None,
    keep_reference_audio: bool = False,
    root: Path | None = None,
) -> ClonedVoice:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Tên giọng không được để trống.")
    if not consent_confirmed:
        raise ValueError("Bạn phải xác nhận quyền sử dụng giọng nói trước khi tạo giọng clone.")
    if str(model_family or "").strip().lower() != "v3turbo":
        raise ValueError("MVP voice cloning chỉ hỗ trợ VieNeu v3 Turbo.")

    import numpy as np

    voice_id = str(uuid.uuid4())
    target = _voice_dir(voice_id, root=root)
    target.mkdir(parents=True, exist_ok=False)
    try:
        np.save(target / "embedding.npy", np.asarray(speaker_embedding, dtype=np.float32), allow_pickle=False)
        codes_file: str | None = None
        if reference_codes is not None:
            np.save(target / "reference_codes.npy", np.asarray(reference_codes, dtype=np.int64), allow_pickle=False)
            codes_file = "reference_codes.npy"
        audio_file: str | None = None
        if keep_reference_audio and reference_audio is not None:
            audio_file = "reference.wav"
            shutil.copy2(reference_audio, target / audio_file)
        voice = ClonedVoice(
            schema_version=1,
            id=voice_id,
            name=clean_name,
            provider="vieneu",
            model_family="v3turbo",
            model_fingerprint=str(model_fingerprint or "").strip(),
            language=str(language or "vi").strip().lower() or "vi",
            description=str(description or "").strip(),
            gender=str(gender or "").strip(),
            speaker_embedding_file="embedding.npy",
            reference_codes_file=codes_file,
            reference_audio_file=audio_file,
            consent_confirmed=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        manifest = target / VOICE_MANIFEST_NAME
        temporary = target / f"{VOICE_MANIFEST_NAME}.tmp"
        temporary.write_text(json.dumps(asdict(voice), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(manifest)
        return voice
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def load_cloned_voice_payload(
    selection_or_id: object,
    *,
    expected_model_family: str = "v3turbo",
    root: Path | None = None,
) -> dict[str, Any]:
    import numpy as np

    voice = get_cloned_voice(selection_or_id, root=root)
    if voice.model_family != str(expected_model_family or "").strip().lower():
        raise ValueError(
            f"Giọng clone {voice.name!r} dành cho {voice.model_family}, "
            f"không tương thích với {expected_model_family}."
        )
    target = _voice_dir(voice.id, root=root)
    embedding_path = target / voice.speaker_embedding_file
    if not embedding_path.is_file():
        raise FileNotFoundError(f"Missing speaker embedding for cloned voice {voice.name!r}")
    codes = None
    if voice.reference_codes_file:
        codes_path = target / voice.reference_codes_file
        if not codes_path.is_file():
            raise FileNotFoundError(f"Missing reference codes for cloned voice {voice.name!r}")
        codes = np.load(codes_path, allow_pickle=False)
    return {
        "description": voice.description,
        "gender": voice.gender,
        "speaker_emb": np.load(embedding_path, allow_pickle=False),
        "codes": codes,
    }


def delete_cloned_voice(selection_or_id: object, *, root: Path | None = None) -> ClonedVoice:
    voice = get_cloned_voice(selection_or_id, root=root)
    shutil.rmtree(_voice_dir(voice.id, root=root))
    return voice
