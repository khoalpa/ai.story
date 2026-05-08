from __future__ import annotations

from image.providers.registry import SDProvider


DEFAULT_MODEL = "runwayml/stable-diffusion-v1-5"


def get_provider() -> SDProvider:
    return SDProvider(
        provider_id="stable_diffusion_local",
        label="Stable Diffusion local",
        renderer="diffusers_local",
        order=10,
        is_local=True,
        uses_diffusers_runtime=True,
        supports_model_browser=True,
        show_model_inventory=True,
        local_caption="stable_diffusion_local runs headless/local through the Python runtime and does not use a URL.",
        missing_model_requires_warning=True,
        default_model=DEFAULT_MODEL,
        preferred_model_suffixes=(".safetensors",),
        prefer_first_model_as_default=True,
        option_groups=(
            "local_model",
            "diffusers_runtime",
            "generation_mode",
            "lora",
            "local_detail_pass",
        ),
    )

