from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from audio.model_store import configure_hf_runtime, provider_cache_dir

_BOOTSTRAP_LOCK = Lock()
_BOOTSTRAPPED = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _load_dotenv_best_effort() -> None:
    candidates = [Path.cwd() / ".env", _repo_root() / ".env"]
    for env_path in candidates:
        for key, value in _parse_env_file(env_path).items():
            os.environ.setdefault(key, value)


def _resolve_cache_dir() -> Path:
    raw = os.environ.get("AI_STUDIO_VIENEU_CACHE_DIR", "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = _repo_root() / path
        return path
    return provider_cache_dir("audio", __file__)


def prefer_gpu_enabled() -> bool:
    value = str(os.environ.get("AI_STUDIO_VIENEU_PREFER_GPU", "1")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def bootstrap_vieneu_runtime(*, allow_network: bool = False) -> None:
    global _BOOTSTRAPPED
    with _BOOTSTRAP_LOCK:
        _load_dotenv_best_effort()

        cache_dir = _resolve_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        configure_hf_runtime(provider="audio", module_file=__file__, allow_network=allow_network)
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

        token = str(os.environ.get("HF_TOKEN", "")).strip()
        if token:
            os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", token)

        offline_requested = str(os.environ.get("AI_STUDIO_VIENEU_OFFLINE", "1")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        offline_mode = offline_requested and not allow_network
        if offline_mode:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
        else:
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)

        _BOOTSTRAPPED = True


__all__ = ["bootstrap_vieneu_runtime", "prefer_gpu_enabled"]
