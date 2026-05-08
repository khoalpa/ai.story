from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RenderImageRequest:
    provider: str
    handoff_dir: Path
    output_dir: Path
    base_url: str = ""
    api_key: str = ""
    workflow_json_file: str = ""
    cover_workflow_json_file: str = ""
    scene_workflow_json_file: str = ""
    fallback_workflow_json_file: str = ""
    auto_select_workflow_by_kind: bool = True
    positive_prompt_node_id: str = "2"
    negative_prompt_node_id: str = "3"
    sampler_node_id: str = "5"
    latent_size_node_id: str = "4"
    output_node_ids: str = "7"
    poll_interval: float = 1.5
    max_wait_s: int = 180
    width: int = 512
    height: int = 768
    steps: int = 30
    cfg: float = 6.5
    sampler_name: str = "dpmpp_2m"
    scheduler: str = "karras"
    seed: int = -1
    negative_prompt: str = ""
    local_model_id_or_path: str = ""
    local_device: str = "auto"
    local_dtype: str = "auto"
    local_variant: str = ""
    local_use_safetensors: bool = True
    local_enable_attention_slicing: bool = True
    local_enable_model_cpu_offload: bool = False
    provider_payload: dict[str, Any] = field(default_factory=dict)
    prompt_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RenderImageResult:
    provider: str
    output_dir: Path
    cover_image: Path | None
    scene_images_dir: Path
    generated_files: list[Path]
    manifest_path: Path | None
    logs: list[str] = field(default_factory=list)

    @property
    def images_dir(self) -> Path:
        return self.scene_images_dir

