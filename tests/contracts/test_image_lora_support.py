from __future__ import annotations

from typing import Any, cast

from image.gui.state import IMAGE_DEFAULTS


def test_image_lora_defaults_are_present() -> None:
    assert IMAGE_DEFAULTS["image_local_lora_enabled"] is False
    assert IMAGE_DEFAULTS["image_local_lora_model_id_or_path"] == ""
    assert IMAGE_DEFAULTS["image_local_lora_scale"] == 1.0


def test_image_settings_exposes_local_lora_controls() -> None:
    from pathlib import Path

    content = Path("image/gui/settings.py").read_text(encoding="utf-8")
    assert "LoRA" in content
    assert "Enable LoRA" in content
    assert "local_lora_model_id_or_path" in content
    assert "local_lora_scale" in content
    assert 'provider_id="lora_local"' in content


def test_image_settings_exposes_comfyui_lora_controls() -> None:
    from pathlib import Path

    content = Path("image/gui/settings.py").read_text(encoding="utf-8")
    assert "ComfyUI LoRA" in content
    assert "Update existing LoRA loader nodes" in content
    assert "image_comfy_lora_model" in content
    assert "style.safetensors" in content


def test_image_provider_loads_lora_weights() -> None:
    from pathlib import Path

    content = Path("image/provider_runtime.py").read_text(encoding="utf-8")
    assert "def _load_local_lora_weights" in content
    assert "load_lora_weights" in content
    assert "set_adapters" in content
    assert "lora_model_ref" in content
    assert "local_lora_enabled" in content


def test_local_lora_loader_skips_missing_adapter_registration() -> None:
    from image.provider_runtime import _load_local_lora_weights

    class Pipe:
        def __init__(self) -> None:
            self.loaded: list[tuple[str, str]] = []
            self.set_calls: list[tuple[list[str], list[float]]] = []

        def load_lora_weights(self, ref: str, *, adapter_name: str) -> None:
            self.loaded.append((ref, adapter_name))

        def get_list_adapters(self) -> dict[str, list[str]]:
            return {}

        def set_adapters(self, names: list[str], adapter_weights: list[float]) -> None:
            self.set_calls.append((names, adapter_weights))
            raise ValueError("Adapter name(s) {'local_lora'} not in the list of present adapters: set().")

    pipe = Pipe()

    _load_local_lora_weights(pipe, lora_ref="style.safetensors", lora_scale=0.7)

    assert pipe.loaded == [("style.safetensors", "local_lora")]
    assert pipe.set_calls == [(["local_lora"], [0.7])]


def test_local_lora_loader_sets_scale_when_adapter_is_present() -> None:
    from image.provider_runtime import _load_local_lora_weights

    class Pipe:
        def __init__(self) -> None:
            self.set_calls: list[tuple[list[str], list[float]]] = []

        def load_lora_weights(self, ref: str, *, adapter_name: str) -> None:
            self.ref = ref
            self.adapter_name = adapter_name

        def get_list_adapters(self) -> dict[str, list[str]]:
            return {"unet": ["local_lora"]}

        def set_adapters(self, names: list[str], adapter_weights: list[float]) -> None:
            self.set_calls.append((names, adapter_weights))

    pipe = Pipe()

    _load_local_lora_weights(pipe, lora_ref="style.safetensors", lora_scale=1.2)

    assert pipe.adapter_name == "local_lora"
    assert pipe.set_calls == [(["local_lora"], [1.2])]


def test_comfyui_workflow_injection_updates_lora_loader_nodes() -> None:
    from image.provider_runtime import _inject_comfyui_workflow

    workflow: dict[str, Any] = {
        "1": {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "old.safetensors",
                "strength_model": 0.25,
                "strength_clip": 0.25,
            },
        },
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    }
    settings: dict[str, Any] = {
        "prompt": "a scene",
        "provider_payload": {
            "local_lora_enabled": True,
            "local_lora_model_id_or_path": "styles/new.safetensors",
            "local_lora_scale": 0.8,
        },
    }

    injected = _inject_comfyui_workflow(workflow, {}, settings)

    inputs = cast(dict[str, Any], injected["1"]["inputs"])
    assert inputs["lora_name"] == "styles/new.safetensors"
    assert inputs["strength_model"] == 0.8
    assert inputs["strength_clip"] == 0.8
    original_inputs = cast(dict[str, Any], workflow["1"]["inputs"])
    assert original_inputs["lora_name"] == "old.safetensors"


def test_comfyui_workflow_injection_updates_rgthree_lora_nodes() -> None:
    from image.provider_runtime import _inject_comfyui_workflow

    workflow: dict[str, Any] = {
        "1": {
            "class_type": "Power Lora Loader (rgthree)",
            "inputs": {
                "lora_1": {"on": False, "lora": "old.safetensors", "strength": 0.25},
            },
        },
    }
    settings: dict[str, Any] = {
        "provider_payload": {
            "local_lora_enabled": True,
            "local_lora_model_id_or_path": r"styles\new.safetensors",
            "local_lora_scale": 1.2,
        },
    }

    injected = _inject_comfyui_workflow(workflow, {}, settings)

    inputs = cast(dict[str, Any], injected["1"]["inputs"])
    lora_input = cast(dict[str, Any], inputs["lora_1"])
    assert lora_input["lora"] == "styles/new.safetensors"
    assert lora_input["strength"] == 1.2
    assert lora_input["on"] is True

