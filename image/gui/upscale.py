from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image
import streamlit as st

from image.gui.state import IMAGE_LAST_UPSCALE_OUTPUT_KEY

_IMAGE_TEMP_COVER_PATH_KEY = "image_temp_cover_path"


def _resolve_prompt_dir(settings: dict[str, Any]) -> Path | None:
    source_kind = str(st.session_state.get("image_source_kind") or "handoff").strip().lower()
    if source_kind == "handoff":
        base_dir = str(settings.get("handoff_dir") or st.session_state.get("image_handoff_dir") or "").strip()
    else:
        base_dir = str(settings.get("input_dir") or st.session_state.get("image_input_dir") or "").strip()
    if not base_dir:
        return None
    return Path(base_dir)


def _list_image_files(dir_value: str | Path | None) -> list[Path]:
    if not dir_value:
        return []
    directory = Path(dir_value)
    if not directory.is_dir():
        return []
    items: list[Path] = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        items.extend(sorted(directory.glob(pattern)))
    deduped: list[Path] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.resolve()) if item.exists() else str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _current_temp_cover_path() -> Path | None:
    value = str(st.session_state.get(_IMAGE_TEMP_COVER_PATH_KEY) or "").strip()
    if not value:
        return None
    path = Path(value)
    if path.is_file():
        return path
    return None


def _collect_upscale_source_candidates(settings: dict[str, Any]) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add(label: str, candidate: Any) -> None:
        if candidate is None:
            return
        candidate_path = Path(str(candidate)).expanduser()
        if not candidate_path.is_file():
            return
        key = str(candidate_path.resolve()) if candidate_path.exists() else str(candidate_path)
        if key in seen:
            return
        seen.add(key)
        candidates.append((label, candidate_path))

    add("Temporary cover", _current_temp_cover_path())
    add("Last upscale output", st.session_state.get(IMAGE_LAST_UPSCALE_OUTPUT_KEY))

    last_result = st.session_state.get("image_last_result")
    if last_result is not None:
        add("Last result cover", getattr(last_result, "cover_image", None))
        for generated_path in list(getattr(last_result, "generated_files", []) or []):
            add(f"Generated file | {Path(str(generated_path)).name}", generated_path)
        scene_images_dir = getattr(last_result, "scene_images_dir", None)
        if scene_images_dir:
            for scene_path in _list_image_files(scene_images_dir):
                add(f"Scene image | {scene_path.name}", scene_path)
        output_dir = getattr(last_result, "output_dir", None)
        if output_dir:
            for output_path in _list_image_files(output_dir):
                add(f"Output image | {output_path.name}", output_path)

    prompt_dir = _resolve_prompt_dir(settings)
    if prompt_dir and prompt_dir.is_dir():
        add("Bundle cover", prompt_dir / "cover.png")
        bundle_scene_dir = prompt_dir / "scene_images"
        for scene_path in _list_image_files(bundle_scene_dir):
            add(f"Bundle scene | {scene_path.name}", scene_path)

    configured_output_dir = str(st.session_state.get("image_output_dir") or settings.get("output_dir") or "").strip()
    if configured_output_dir:
        output_dir = Path(configured_output_dir)
        if output_dir.is_dir():
            for path_value in _list_image_files(output_dir):
                add(f"Output folder | {path_value.name}", path_value)

    return candidates


def _upscale_image_file(source_path: Path, *, scale: float, resample: str, output_dir_value: str = "") -> tuple[Path, Image.Image]:
    resample_map = {
        "nearest": Image.Resampling.NEAREST,
        "bilinear": Image.Resampling.BILINEAR,
        "bicubic": Image.Resampling.BICUBIC,
        "lanczos": Image.Resampling.LANCZOS,
    }
    resample_mode = resample_map.get(str(resample or "").strip().lower(), Image.Resampling.LANCZOS)
    scale_value = max(1.0, float(scale))
    with Image.open(source_path) as source_img:
        base_img = source_img.convert("RGB")
    new_width = max(1, int(round(base_img.width * scale_value)))
    new_height = max(1, int(round(base_img.height * scale_value)))
    upscaled = base_img.resize((new_width, new_height), resample=resample_mode)

    if output_dir_value.strip():
        output_dir = Path(output_dir_value).expanduser()
    else:
        output_dir = source_path.parent / "upscaled"
    output_dir.mkdir(parents=True, exist_ok=True)
    scale_label = str(scale_value).replace(".", "p").rstrip("0").rstrip("p")
    output_path = output_dir / f"{source_path.stem}_upscaled_x{scale_label}.png"
    suffix = 2
    while output_path.exists():
        output_path = output_dir / f"{source_path.stem}_upscaled_x{scale_label}_{suffix}.png"
        suffix += 1
    upscaled.save(output_path)
    return output_path, upscaled

