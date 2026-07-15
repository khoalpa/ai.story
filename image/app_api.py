from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def render_image_workspace(*, embedded: bool = False) -> None:
    """Render Image's GUI while keeping Streamlit out of headless imports."""
    from image.gui.app import render_image_workspace as render

    render(embedded=embedded)


def render_image_studio(*args: Any, **kwargs: Any) -> None:
    kwargs.setdefault("embedded", True)
    render_image_workspace(*args, **kwargs)


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


def validate_request(request: RenderImageRequest) -> None:
    if not isinstance(request, RenderImageRequest):
        raise TypeError("request must be RenderImageRequest")
    if not request.provider.strip():
        raise ValueError("provider is required")
    if request.width <= 0 or request.height <= 0:
        raise ValueError("image dimensions must be positive")


def execute_request(request: RenderImageRequest, progress_callback=None) -> RenderImageResult:
    validate_request(request)
    from image.gui.service import run_image_job

    return run_image_job(request, progress_callback=progress_callback)


__all__ = [
    "RenderImageRequest", "RenderImageResult", "execute_request",
    "render_image_studio", "render_image_workspace", "validate_request",
]

