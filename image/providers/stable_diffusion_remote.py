from __future__ import annotations

from image.providers.registry import SDProvider


def get_provider() -> SDProvider:
    return SDProvider(
        provider_id="stable_diffusion_remote",
        label="Stable Diffusion remote (A1111)",
        renderer="a1111_remote",
        order=20,
        requires_base_url=True,
        default_base_url="http://127.0.0.1:7860",
        uses_api_key=True,
        option_groups=("remote_endpoint",),
    )

