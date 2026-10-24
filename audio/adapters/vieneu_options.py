"""Pure VieNeu option normalization and supported defaults."""
from __future__ import annotations

from audio.exceptions import TtsError

DEFAULT_VIENEU_MODE = "standard"


SUPPORTED_VIENEU_MODES = (
    "v3turbo",
    "v4",
    "turbo",
    "standard",
    "remote",
    "api",
    "fast",
    "cuda",
    "turbo_gpu",
    "xpu",
)


DEFAULT_VIENEU_TURBO_MODEL_NAME = "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF"


DEFAULT_VIENEU_V3_TURBO_MODEL_NAME = "pnnbao-ump/VieNeu-TTS-v3-Turbo"


DEFAULT_VIENEU_V4_MODEL_NAME = "VieNeu-TTS-v4"


DEFAULT_VIENEU_STANDARD_MODEL_NAME = "pnnbao-ump/VieNeu-TTS"


DEFAULT_VIENEU_MODEL_NAME = DEFAULT_VIENEU_STANDARD_MODEL_NAME


DEFAULT_VIENEU_STANDARD_CODEC_REPO = "neuphonic/distill-neucodec"


DEFAULT_VIENEU_STANDARD_DISTILHUBERT_REPO = "ntu-spml/distilhubert"


VIENEU_V3_CODEC_FILES = (
    "codec_browser_onnx_meta.json",
    "moss_audio_tokenizer_decode_full.onnx",
    "moss_audio_tokenizer_decode_shared.data",
    "moss_audio_tokenizer_decode_step.onnx",
    "moss_audio_tokenizer_encode.data",
    "moss_audio_tokenizer_encode.onnx",
)


DEFAULT_VIENEU_API_BASE = "http://127.0.0.1:23333/v1"


DEFAULT_VIENEU_DEVICE = "auto"


def normalize_vieneu_mode(value: object) -> str:
    normalized = str(value or DEFAULT_VIENEU_MODE).strip().lower().replace("-", "_")
    aliases = {
        "v3": "v3turbo",
        "v3_turbo": "v3turbo",
        "v3turbo": "v3turbo",
        "v4": "v4",
        "local": "turbo",
        "default": "turbo",
        "turbo": "turbo",
        "standard": "standard",
        "remote": "remote",
        "api": "remote",
        "fast": "fast",
        "gpu": "fast",
        "cuda": "fast",
        "turbo_gpu": "turbo_gpu",
        "xpu": "xpu",
    }
    mode = aliases.get(normalized)
    if mode:
        return mode
    raise TtsError(
        f"VieNeu TTS core mode không hợp lệ: {value!r}. Hỗ trợ: {', '.join(SUPPORTED_VIENEU_MODES)}"
    )


def is_vieneu_v3_turbo_model(model_name: object) -> bool:
    clean_model = str(model_name or "").strip().lower().replace("-", "_")
    return "v3" in clean_model and "turbo" in clean_model


def resolve_vieneu_effective_mode(
    core: object,
    mode: object,
    device: object | None = None,
    model_name: object | None = None,
) -> str:
    selected_core = str(core or "local").strip().lower().replace("-", "_").replace(" ", "_")
    selected_mode = normalize_vieneu_mode(mode)
    _ = device, model_name
    if selected_core in {"remote", "remote_api", "api", "remoteapi"} or selected_mode == "v4":
        return "remote"
    return selected_mode


def normalize_vieneu_device(value: object) -> str:
    normalized = str(value or DEFAULT_VIENEU_DEVICE).strip().lower().replace("-", "_")
    aliases = {
        "auto": "auto",
        "default": "auto",
        "prefer_gpu": "auto",
        "gpu": "cuda",
        "cuda": "cuda",
        "cuda:0": "cuda",
        "cpu": "cpu",
    }
    device = aliases.get(normalized)
    if device:
        return device
    raise TtsError(f"VieNeu runtime device is invalid: {value!r}. Supported: auto, cuda, cpu")


def normalize_vieneu_backend(value: object) -> str:
    normalized = str(value or "auto").strip().lower().replace("-", "_")
    if normalized in {"auto", "native", "lmdeploy"}:
        return normalized
    if normalized in {"default", "prefer_native"}:
        return "auto"
    return "auto"
