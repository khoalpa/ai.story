"""Static adapter registry; target names never trigger dynamic imports."""
from __future__ import annotations

from studio.video_prompt_adapters.base import VideoPromptAdapter
from studio.video_prompt_adapters.flow import ADAPTER as FLOW_ADAPTER
from studio.video_prompt_adapters.generic import ADAPTER as GENERIC_ADAPTER
from studio.video_prompt_adapters.veo import ADAPTER as VEO_ADAPTER

_ADAPTERS: dict[str, VideoPromptAdapter] = {
    adapter.target: adapter for adapter in (VEO_ADAPTER, FLOW_ADAPTER, GENERIC_ADAPTER)
}


def adapter_targets() -> tuple[str, ...]:
    return tuple(_ADAPTERS)


def get_adapter(target: str) -> VideoPromptAdapter:
    normalized = target.upper()
    try:
        return _ADAPTERS[normalized]
    except KeyError as exc:
        raise ValueError(f"Chưa có adapter deterministic cho target {target!r}") from exc


__all__ = ["adapter_targets", "get_adapter"]
