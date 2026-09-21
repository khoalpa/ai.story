from __future__ import annotations

import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from audio.adapters.tts_core import get_vieneu_engine, resolve_vieneu_model_for_runtime
from audio.vieneu_voice_store import (
    ClonedVoice,
    load_cloned_voice_payload,
    save_cloned_voice,
)


@dataclass(frozen=True)
class ReferenceAudioQuality:
    duration_seconds: float
    sample_rate: int
    channels: int
    warning: str | None = None


def normalize_reference_audio(source: Path, destination: Path, *, ffmpeg_exe: str = "ffmpeg") -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(destination),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not destination.is_file():
        detail = str(result.stderr or "").strip()
        raise ValueError(f"Không thể chuẩn hóa audio tham chiếu bằng FFmpeg. {detail}".strip())
    return destination


def inspect_reference_audio(path: Path) -> ReferenceAudioQuality:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
    duration = frames / sample_rate if sample_rate else 0.0
    warning = None
    if duration < 3.0:
        warning = "Mẫu quá ngắn; nên dùng 10–30 giây giọng nói rõ ràng."
    elif duration > 60.0:
        warning = "Mẫu dài hơn 60 giây; nên cắt còn 10–30 giây để enroll nhanh và ổn định."
    return ReferenceAudioQuality(duration, sample_rate, channels, warning)


def create_cloned_voice(
    *,
    reference_audio: Path,
    name: str,
    consent_confirmed: bool,
    language: str = "vi",
    description: str = "",
    gender: str = "",
    keep_reference_audio: bool = False,
    model_name: str = "",
    device: str = "cuda",
    backend: str = "auto",
    ffmpeg_exe: str = "ffmpeg",
) -> tuple[ClonedVoice, ReferenceAudioQuality]:
    if not consent_confirmed:
        raise ValueError("Bạn phải xác nhận quyền sử dụng giọng nói trước khi tạo giọng clone.")
    with tempfile.TemporaryDirectory(prefix="ai_studio_voice_clone_") as temporary_dir:
        normalized = normalize_reference_audio(
            Path(reference_audio), Path(temporary_dir) / "reference.wav", ffmpeg_exe=ffmpeg_exe
        )
        quality = inspect_reference_audio(normalized)
        runtime_model = resolve_vieneu_model_for_runtime(model_name, "v3turbo", allow_network=False)
        engine = get_vieneu_engine(
            mode="v3turbo", model_name=model_name, device=device, backend=backend, allow_network=False
        )
        encode = getattr(engine, "encode_reference", None)
        if not callable(encode):
            raise RuntimeError("VieNeu runtime hiện tại không hỗ trợ encode_reference cho v3 Turbo.")
        speaker_embedding, reference_codes = encode(normalized)
        voice = save_cloned_voice(
            name=name,
            speaker_embedding=speaker_embedding,
            reference_codes=reference_codes,
            language=language,
            description=description,
            gender=gender,
            model_family="v3turbo",
            model_fingerprint=str(runtime_model or model_name or "v3turbo"),
            consent_confirmed=True,
            reference_audio=normalized,
            keep_reference_audio=keep_reference_audio,
        )
        return voice, quality


def preview_cloned_voice(
    selection_id: str,
    *,
    text: str,
    output_path: Path,
    model_name: str = "",
    device: str = "cuda",
    backend: str = "auto",
    temperature: float = 0.6,
) -> Path:
    clean_text = str(text or "").strip()
    if not clean_text:
        raise ValueError("Văn bản nghe thử không được để trống.")
    engine = get_vieneu_engine(
        mode="v3turbo", model_name=model_name, device=device, backend=backend, allow_network=False
    )
    payload = load_cloned_voice_payload(selection_id, expected_model_family="v3turbo")
    audio = engine.infer(text=clean_text, voice=payload, temperature=float(temperature), max_chars=160)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    engine.save(audio, output_path)
    return output_path
