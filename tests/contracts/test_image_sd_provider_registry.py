from __future__ import annotations

from pathlib import Path


def test_sd_provider_registry_discovers_provider_modules() -> None:
    from image.providers import get_sd_provider_choices, list_sd_provider_ids, list_sd_providers

    provider_ids = list_sd_provider_ids()

    assert provider_ids == [
        "stable_diffusion_local",
        "stable_diffusion_remote",
        "comfyui_local",
        "comfyui_remote",
    ]
    assert get_sd_provider_choices()["stable_diffusion_local"] == "Stable Diffusion local"
    assert all(provider.option_groups for provider in list_sd_providers())


def test_image_sidebar_uses_sd_provider_registry_for_dropdown() -> None:
    content = Path("image/gui/settings.py").read_text(encoding="utf-8")

    assert "list_sd_provider_ids()" in content
    assert "get_sd_provider_choices()" in content
    assert 'provider_options = [\n            "stable_diffusion_local"' not in content


def test_comfyui_remote_exposes_workflow_preview_option_group() -> None:
    from image.providers import get_sd_provider

    provider = get_sd_provider("comfyui_remote")

    assert "workflow_preview" in provider.option_groups


def test_render_dispatch_uses_provider_renderer_metadata() -> None:
    content = Path("image/provider_runtime.py").read_text(encoding="utf-8")

    assert "provider_meta = get_sd_provider(provider)" in content
    assert 'if provider == "stable_diffusion_local"' not in content

