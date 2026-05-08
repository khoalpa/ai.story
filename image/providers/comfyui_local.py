from __future__ import annotations

from image.providers.registry import SDProvider


def get_provider() -> SDProvider:
    return SDProvider(
        provider_id="comfyui_local",
        label="ComfyUI local",
        renderer="comfyui_local",
        order=30,
        is_local=True,
        is_comfyui=True,
        supports_model_browser=True,
        show_model_inventory=True,
        local_caption="comfyui_local runs headless/local through the built-in workflow interpreter and does not use a URL.",
        option_groups=(
            "local_model",
            "generation_mode",
            "comfyui_routing",
            "comfyui_lora",
            "workflow_preview",
        ),
    )

