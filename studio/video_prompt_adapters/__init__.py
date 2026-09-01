"""Target-specific adapters for canonical video prompt plans."""
from studio.video_prompt_adapters.base import VideoPromptAdapter
from studio.video_prompt_adapters.registry import adapter_targets, get_adapter

__all__ = ["VideoPromptAdapter", "adapter_targets", "get_adapter"]
