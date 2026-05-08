from __future__ import annotations

from pathlib import Path
from typing import Any

from common.gui.view_model_utils import path_to_text, pick_mapping_values


_IMAGE_SETTINGS_FIELDS = (
    "provider",
    "width",
    "height",
    "steps",
    "cfg",
    "sampler_name",
    "scheduler",
    "output_dir",
)


def build_image_run_summary(
    *,
    settings: dict[str, Any],
    prompt_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    summary = pick_mapping_values(settings, _IMAGE_SETTINGS_FIELDS)
    summary.update({
        "prompt_path": path_to_text(prompt_path),
        "output_path": path_to_text(output_path),
    })
    return summary


