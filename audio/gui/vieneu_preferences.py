"""Normalize persisted VieNeu UI preferences."""
from __future__ import annotations


def _normalize_vieneu_device_choice(value: object) -> str:
    normalized = str(value or "auto").strip().lower().replace("-", "_")
    if normalized == "cpu":
        return "cpu"
    if normalized in {"auto", "cuda", "gpu", "cuda:0", "cuda0", "default", "prefer_gpu"}:
        return "auto"
    return "auto"


def _normalize_vieneu_backend_choice(value: object) -> str:
    normalized = str(value or "auto").strip().lower().replace("-", "_")
    if normalized in {"auto", "native", "lmdeploy"}:
        return normalized
    return "auto"
