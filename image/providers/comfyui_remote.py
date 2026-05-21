from __future__ import annotations

from image.providers.registry import SDProvider


def get_provider() -> SDProvider:
    return SDProvider(
        provider_id="comfyui_remote",
        label="ComfyUI remote",
        renderer="comfyui_remote",
        order=40,
        requires_base_url=True,
        default_base_url="http://127.0.0.1:8188",
        uses_api_key=True,
        is_comfyui=True,
        option_groups=("remote_endpoint", "comfyui_routing", "comfyui_lora", "workflow_preview"),
    )

