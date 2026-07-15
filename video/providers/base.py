from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from video.runtime_diagnostics import RuntimeDiagnosticsReport


@dataclass(frozen=True)
class VideoProviderSettings:
    provider: str
    ffmpeg_exe: str = ""
    ffprobe_exe: str = ""
    local_update_target: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ffmpeg_exe": self.ffmpeg_exe,
            "ffprobe_exe": self.ffprobe_exe,
            "local_update_target": self.local_update_target,
            **self.extra,
        }


@dataclass(frozen=True)
class VideoProviderDescriptor:
    provider_id: str
    label: str
    description: str
    render_sidebar: Callable[[], VideoProviderSettings]
    aliases: tuple[str, ...] = ()
    sort_order: int = 100
    collect_runtime_diagnostics: Callable[[dict[str, Any]], RuntimeDiagnosticsReport] | None = None


def normalize_provider_token(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
