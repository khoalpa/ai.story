from __future__ import annotations

from image.provider_runtime import _merge_prompt_settings


def test_image_generation_parameters_come_from_sidebar_settings() -> None:
    merged = _merge_prompt_settings(
        {
            "prompt": "story handoff prompt",
            "negative_prompt": "workspace negative",
            "width": 832,
            "height": 1472,
            "steps": 32,
            "cfg": 6.5,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "seed": 111,
            "provider_payload": {
                "local_generation_mode": "txt2img",
                "guidance_scale": 6.5,
                "story_only": True,
            },
        },
        {
            "width": 512,
            "height": 768,
            "steps": 20,
            "cfg": 4.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "seed": 222,
            "provider_payload": {
                "local_generation_mode": "controlnet",
                "guidance_scale": 4.0,
                "sidebar_only": True,
            },
        },
    )

    assert merged["prompt"] == "story handoff prompt"
    assert merged["negative_prompt"] == "workspace negative"
    assert merged["width"] == 512
    assert merged["height"] == 768
    assert merged["steps"] == 20
    assert merged["cfg"] == 4.0
    assert merged["sampler_name"] == "euler"
    assert merged["scheduler"] == "normal"
    assert merged["seed"] == 222
    assert merged["provider_payload"] == {
        "local_generation_mode": "controlnet",
        "guidance_scale": 4.0,
        "story_only": True,
        "sidebar_only": True,
    }


def test_image_generation_size_falls_back_to_prompt_when_sidebar_size_missing() -> None:
    merged = _merge_prompt_settings(
        {
            "prompt": "standalone prompt",
            "width": 832,
            "height": 1472,
        },
        {},
    )

    assert merged["width"] == 832
    assert merged["height"] == 1472

