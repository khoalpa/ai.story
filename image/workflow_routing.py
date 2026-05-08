from __future__ import annotations

from pathlib import Path
from typing import Any

from image.runtime import resolve_image_assets_root

ZONE_KEYS = {
    "intro_card",
    "greeting",
    "opening",
    "introduction",
    "development",
    "climax",
    "falling",
    "ending",
    "farewell",
    "outro_card",
}

DEFAULT_COMFYUI_WORKFLOW = "comfyui_minimal_t2i_workflow.json"


def default_comfyui_workflow_file() -> str:
    workflow = resolve_image_assets_root(__file__) / "workflows" / DEFAULT_COMFYUI_WORKFLOW
    return str(workflow) if workflow.is_file() else ""


def infer_prompt_kind(prompt_data: dict[str, Any], prompt_path: Path | None = None) -> str:
    kind = str(prompt_data.get("kind") or "").strip().lower()
    if kind in {"cover", "scene"}:
        return kind
    slot = str(prompt_data.get("slot") or prompt_data.get("image_key") or "").strip().lower()
    if slot == "cover" or "cover" in slot:
        return "cover"
    if slot in ZONE_KEYS or slot == "scene_overview":
        return "scene"
    if prompt_path is not None:
        name = prompt_path.name.lower()
        if "cover" in name:
            return "cover"
        if any(zone in name for zone in ZONE_KEYS) or "scene" in name:
            return "scene"
    return "scene"


def resolve_workflow_file(*, prompt_data: dict[str, Any], prompt_path: Path | None, settings: dict[str, Any]) -> str:
    provider = str(settings.get("provider") or "").strip().lower()
    if not provider.startswith("comfyui"):
        return str(settings.get("workflow_json_file") or "")

    fallback = str(settings.get("fallback_workflow_json_file") or "") or default_comfyui_workflow_file()

    auto_route = bool(settings.get("auto_select_workflow_by_kind", True))
    if not auto_route:
        return str(settings.get("workflow_json_file") or fallback)

    kind = infer_prompt_kind(prompt_data, prompt_path)
    if kind == "cover":
        return str(
            settings.get("cover_workflow_json_file")
            or settings.get("workflow_json_file")
            or fallback
        )

    return str(
        settings.get("scene_workflow_json_file")
        or settings.get("workflow_json_file")
        or fallback
    )

