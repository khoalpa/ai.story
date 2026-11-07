"""Provider boundary for Summary image generation.

Providers return image bytes only. Planning, retries, validation, persistence, and
package state remain the responsibility of the Summary orchestrator.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ImageGenerationRequest:
    asset_id: str
    scene_id: str
    orientation: str
    prompt: str
    output_path: str
    reference_paths: tuple[Path, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    model: str | None = None
    generation_id: str | None = None
    seed: str | int | None = None


class SummaryImageProvider(Protocol):
    """Small provider surface suitable for hosted or local image generators."""

    @property
    def name(self) -> str: ...

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage: ...


class CommandImageProvider:
    """Run an explicit local adapter that accepts JSON stdin and emits image bytes.

    The adapter receives references as paths and may write diagnostic text to
    stderr. A non-zero exit, timeout, or empty stdout is treated as a tool failure.
    This provider is only constructed when the CLI user explicitly supplies an
    executable; no command is discovered or run implicitly.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: int = 300,
        provider_name: str = "command",
    ) -> None:
        if not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError("Provider command không hợp lệ")
        if not 1 <= timeout_seconds <= 3600:
            raise ValueError("Provider timeout phải từ 1 đến 3600 giây")
        self._command = tuple(command)
        self._timeout_seconds = timeout_seconds
        self._name = provider_name

    @property
    def name(self) -> str:
        return self._name

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        payload = {
            "schema_version": "1.0.0",
            "asset_id": request.asset_id,
            "scene_id": request.scene_id,
            "orientation": request.orientation,
            "prompt": request.prompt,
            "output_path": request.output_path,
            "reference_paths": [str(path.resolve()) for path in request.reference_paths],
            "metadata": dict(request.metadata),
        }
        try:
            completed = subprocess.run(
                self._command,
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                capture_output=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Image provider không chạy được: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Image provider thất bại ({completed.returncode}): "
                f"{detail or 'không có chi tiết'}"
            )
        if not completed.stdout:
            raise RuntimeError("Image provider trả dữ liệu ảnh rỗng")
        return GeneratedImage(completed.stdout)


__all__ = [
    "CommandImageProvider",
    "GeneratedImage",
    "ImageGenerationRequest",
    "SummaryImageProvider",
]
