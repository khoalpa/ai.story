from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image
import streamlit as st

from common.gui.history_utils import append_deduped_tail_history_entry
from image.gui.common_ui import _normalize_exc, _ui_info, _ui_success, _ui_warning
from image.gui.result_ui import _current_temp_cover_path, _find_scene_output_by_key
from image.gui.state import IMAGE_INPAINT_MASK_PATH_KEY, IMAGE_INPAINT_SOURCE_PATH_KEY
from image.provider_runtime import (
    _resolve_bundle_asset_path,
    build_debug_preview_sheet,
    overlay_mask_preview,
    parse_preview_tint,
)

# Source resolution helpers
def _resolve_inpaint_source_for_entry(settings: dict[str, Any], prompt_dir: Path | None, entry: dict[str, Any]) -> tuple[Path | None, str]:
    prompt_path = entry.get("path")
    prompt_data = dict(entry.get("prompt_data") or {})
    provider_payload = dict(settings.get("provider_payload") or {})
    source_kind = "inpaint_image" if str(provider_payload.get("local_generation_mode") or "") == "inpaint" else "init_image"
    resolved = _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind=source_kind)
    if resolved is None:
        resolved = _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind="init_image")
    if resolved is None:
        return None, ""
    return resolved, str(resolved)


# Canvas compatibility helpers
def _install_drawable_canvas_image_shim() -> None:
    try:
        import streamlit.elements.image as st_image
    except Exception:
        return
    if hasattr(st_image, "image_to_url"):
        return

    def _fallback_image_to_url(image: Any, *args: Any, **kwargs: Any) -> str:
        if isinstance(image, str):
            return image
        if isinstance(image, bytes):
            return f"data:image/png;base64,{base64.b64encode(image).decode('ascii')}"
        if isinstance(image, Image.Image):
            fmt = str(kwargs.get("output_format") or "PNG").upper().strip()
            buffer = io.BytesIO()
            save_format = fmt if fmt in {"PNG", "JPEG", "WEBP"} else "PNG"
            image.save(buffer, format=save_format)
            mime = "image/jpeg" if save_format == "JPEG" else f"image/{save_format.lower()}"
            return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
        return ""

    st_image.image_to_url = _fallback_image_to_url


def _ensure_streamlit_canvas_compat() -> None:
    _install_drawable_canvas_image_shim()


# Source candidate discovery
def _collect_inpaint_source_candidates(settings: dict[str, Any], prompt_dir: Path | None, entry: dict[str, Any]) -> list[tuple[str, Path]]:
    prompt_path = entry.get("path")
    prompt_data = dict(entry.get("prompt_data") or {})
    provider_payload = dict(settings.get("provider_payload") or {})
    source_kind = "inpaint_image" if str(provider_payload.get("local_generation_mode") or "") == "inpaint" else "init_image"
    rel_path = str(entry.get("rel_path") or Path(str(prompt_path)).name).strip()
    candidates: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add_candidate(label: str, candidate: Any) -> None:
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

    resolved = _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind=source_kind)
    if resolved is None:
        resolved = _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind="init_image")
    add_candidate("Resolved source", resolved)
    add_candidate("Bundle init image", _resolve_bundle_asset_path(prompt_path=prompt_path, prompt_data=prompt_data, provider_payload=provider_payload, asset_kind="init_image"))
    add_candidate("Uploaded source", _current_uploaded_inpaint_source_path(rel_path))

    fallback_candidates: list[tuple[str, str]] = [
        ("Session inpaint source", str(st.session_state.get(IMAGE_INPAINT_SOURCE_PATH_KEY) or "")),
        ("Local inpaint image", str(st.session_state.get("image_local_inpaint_image") or "")),
        ("Editor source", str(st.session_state.get("image_inpaint_editor_source_path") or "")),
        ("Temporary cover", str(_current_temp_cover_path() or "")),
    ]
    last_result = st.session_state.get("image_last_result")
    if last_result is not None:
        fallback_candidates.extend([
            ("Last result cover", str(getattr(last_result, "cover_image", None) or "")),
            ("Last result output cover", str(st.session_state.get("image_last_cover_output") or "")),
        ])
        scene_images_dir = str(getattr(last_result, "scene_images_dir", "") or "")
        image_key = str(prompt_data.get("image_key") or "").strip()
        if scene_images_dir and image_key:
            scene_dir = Path(scene_images_dir)
            scene_match = _find_scene_output_by_key(scene_dir, image_key=image_key)
            if scene_match is not None:
                add_candidate("Last result scene", scene_match)

    for label, candidate in fallback_candidates:
        candidate_path = Path(candidate).expanduser() if candidate else None
        if candidate_path is not None and candidate_path.is_file():
            add_candidate(label, candidate_path)

    return candidates


def _inpaint_uploaded_source_key(rel_path: str) -> str:
    return f"image_inpaint_uploaded_source_path::{rel_path}"


def _inpaint_source_upload_widget_key(rel_path: str) -> str:
    return f"image_inpaint_source_upload::{rel_path}"


def _inpaint_manual_source_key(rel_path: str) -> str:
    return f"image_inpaint_manual_source::{rel_path}"


def _inpaint_uploaded_source_clear_key(rel_path: str) -> str:
    return f"image_inpaint_uploaded_source_clear::{rel_path}"


# Upload / preview / badge helpers
def _current_uploaded_inpaint_source_path(rel_path: str) -> Path | None:
    value = str(st.session_state.get(_inpaint_uploaded_source_key(rel_path)) or "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_file() else None


def _has_uploaded_inpaint_source(rel_path: str) -> bool:
    return _current_uploaded_inpaint_source_path(rel_path) is not None


def _get_uploaded_inpaint_source_metadata(rel_path: str) -> tuple[Path | None, str]:
    path = _current_uploaded_inpaint_source_path(rel_path)
    if path is None:
        return None, ""
    return path, f"Uploaded source | {path.name}"


def _can_apply_manual_inpaint_source(*, uploaded_source_path_value: Path | None, uploaded_source: Path | None) -> bool:
    return uploaded_source_path_value is None and uploaded_source is None


def _is_uploaded_inpaint_preview_source(*, source_path: Path | None, uploaded_source_path_value: Path | None) -> bool:
    return (
        uploaded_source_path_value is not None
        and source_path is not None
        and source_path.is_file()
        and Path(str(source_path)).resolve() == Path(str(uploaded_source_path_value)).resolve()
    )


def _inpaint_preview_source_caption(*, source_label: str, is_uploaded_preview: bool) -> str:
    return "Source image: Uploaded preview source" if is_uploaded_preview else f"Source image: {source_label}"


def _inpaint_preview_source_badge_text(*, is_uploaded_preview: bool) -> str:
    return "Uploaded preview source" if is_uploaded_preview else ""


def _inpaint_source_status_badge_text(*, uploaded_source_active: bool) -> str:
    return "Uploaded source active" if uploaded_source_active else "Auto-resolved source"


def _store_uploaded_inpaint_source(uploaded_file: Any, *, prompt_dir: Path | None, selected_rel_path: str) -> Path:
    base_dir = (prompt_dir or Path.cwd()) / ".inpaint_uploads"
    base_dir.mkdir(parents=True, exist_ok=True)
    original_name = Path(str(getattr(uploaded_file, "name", "") or "uploaded.png")).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        suffix = ".png"
    stem = Path(original_name).stem or "uploaded"
    rel_hash = hashlib.sha1(selected_rel_path.encode("utf-8")).hexdigest()[:12]
    target = base_dir / f"{stem}_{rel_hash}_uploaded{suffix}"
    target.write_bytes(uploaded_file.getvalue())
    st.session_state[_inpaint_uploaded_source_key(selected_rel_path)] = str(target)
    return target


def _clear_uploaded_inpaint_source(*, selected_rel_path: str) -> None:
    uploaded_path = _current_uploaded_inpaint_source_path(selected_rel_path)
    if uploaded_path is not None:
        try:
            uploaded_path.unlink(missing_ok=True)
        except Exception:
            pass
    for key in (
        _inpaint_uploaded_source_key(selected_rel_path),
        _inpaint_source_upload_widget_key(selected_rel_path),
        _inpaint_manual_source_key(selected_rel_path),
        _inpaint_uploaded_source_clear_key(selected_rel_path),
    ):
        st.session_state.pop(key, None)


# Temp cover keys
_IMAGE_TEMP_COVER_PATH_KEY = "image_temp_cover_path"
_IMAGE_TEMP_COVER_SOURCE_KEY = "image_temp_cover_source"


# Canvas state helpers
def _canvas_state_key(rel_path: str) -> str:
    return f"image_inpaint_canvas_state::{rel_path}"


def _canvas_rev_key(rel_path: str) -> str:
    return f"image_inpaint_canvas_rev::{rel_path}"


def _canvas_mode_key(rel_path: str) -> str:
    return f"image_inpaint_canvas_mode::{rel_path}"


def _canvas_history_key(rel_path: str) -> str:
    return f"image_inpaint_canvas_history::{rel_path}"


def _canvas_json_key(rel_path: str) -> str:
    return f"image_inpaint_canvas_json::{rel_path}"


def _canvas_auto_load_key(rel_path: str) -> str:
    return f"image_inpaint_canvas_auto_loaded::{rel_path}"


def _canvas_seed_state(rel_path: str) -> dict[str, Any]:
    current = st.session_state.get(_canvas_state_key(rel_path))
    if isinstance(current, dict) and isinstance(current.get("objects"), list):
        return current
    return {"version": "4.4.0", "objects": []}


def _push_canvas_history(rel_path: str, state: dict[str, Any]) -> None:
    append_deduped_tail_history_entry(
        _canvas_history_key(rel_path),
        json.loads(json.dumps(state)),
        limit=20,
    )


def _set_canvas_state(rel_path: str, state: dict[str, Any]) -> None:
    normalized = state if isinstance(state, dict) else {"version": "4.4.0", "objects": []}
    if "objects" not in normalized or not isinstance(normalized.get("objects"), list):
        normalized = {"version": "4.4.0", "objects": []}
    st.session_state[_canvas_state_key(rel_path)] = normalized
    st.session_state[_canvas_json_key(rel_path)] = normalized


def _undo_canvas(rel_path: str) -> None:
    history = list(st.session_state.get(_canvas_history_key(rel_path)) or [])
    if len(history) <= 1:
        _set_canvas_state(rel_path, {"version": "4.4.0", "objects": []})
        st.session_state[_canvas_history_key(rel_path)] = []
    else:
        history.pop()
        previous = history[-1]
        st.session_state[_canvas_history_key(rel_path)] = history
        _set_canvas_state(rel_path, previous)
    st.session_state[_canvas_rev_key(rel_path)] = int(st.session_state.get(_canvas_rev_key(rel_path)) or 0) + 1


def _clear_canvas(rel_path: str) -> None:
    _set_canvas_state(rel_path, {"version": "4.4.0", "objects": []})
    st.session_state[_canvas_history_key(rel_path)] = []
    st.session_state[_canvas_rev_key(rel_path)] = int(st.session_state.get(_canvas_rev_key(rel_path)) or 0) + 1


# Mask/preview helpers
def _preview_sheet_export_path(prompt_dir: Path | None, selected_rel_path: str, image_key: str) -> Path:
    base_dir = prompt_dir or Path.cwd()
    export_dir = base_dir / "debug_previews"
    export_dir.mkdir(parents=True, exist_ok=True)
    stem = image_key.strip() or Path(selected_rel_path).stem
    return export_dir / f"{stem}_preview_sheet.png"


def _hex_to_rgb(color_value: str) -> tuple[int, int, int]:
    return parse_preview_tint(color_value)


def _canvas_image_to_mask(image_data: Any) -> Image.Image | None:
    if image_data is None:
        return None
    try:
        import numpy as np
    except Exception:
        return None

    rgba = np.asarray(image_data)
    if rgba.ndim < 2:
        return None

    if rgba.ndim == 2:
        alpha = rgba > 0
        brightness = rgba
    else:
        if rgba.shape[2] < 3:
            return None
        if rgba.shape[2] >= 4:
            alpha = rgba[:, :, 3] > 0
        else:
            alpha = np.ones(rgba.shape[:2], dtype=bool)
        rgb = rgba[:, :, :3].astype("uint16")
        brightness = rgb.mean(axis=2)

    mask = alpha & (brightness >= 128)
    return Image.fromarray((mask.astype("uint8") * 255), mode="L")


def _sync_inpaint_selection_to_settings(*, source_path: Path, mask_path: Path) -> None:
    source_value = str(source_path)
    mask_value = str(mask_path)
    st.session_state["image_local_generation_mode"] = "inpaint"
    st.session_state["image_local_inpaint_image"] = source_value
    st.session_state["image_local_inpaint_mask"] = mask_value
    st.session_state[IMAGE_INPAINT_SOURCE_PATH_KEY] = source_value
    st.session_state[IMAGE_INPAINT_MASK_PATH_KEY] = mask_value


def _mask_image_to_canvas_state(mask_image: Image.Image) -> dict[str, Any]:
    mask = mask_image.convert("L")
    width, height = mask.size
    pixels = mask.load()

    active: dict[tuple[int, int], dict[str, int]] = {}
    rects: list[dict[str, int]] = []

    for y in range(height):
        row_runs: list[tuple[int, int]] = []
        x = 0
        while x < width:
            while x < width and pixels[x, y] < 128:
                x += 1
            start = x
            while x < width and pixels[x, y] >= 128:
                x += 1
            if start < x:
                row_runs.append((start, x))

        next_active: dict[tuple[int, int], dict[str, int]] = {}
        for run in row_runs:
            if run in active:
                rect = active[run]
                rect["height"] += 1
                next_active[run] = rect
            else:
                next_active[run] = {"left": run[0], "top": y, "width": max(1, run[1] - run[0]), "height": 1}

        for run, rect in active.items():
            if run not in next_active:
                rects.append(rect)
        active = next_active

    rects.extend(active.values())
    objects: list[dict[str, Any]] = []
    for rect in rects:
        objects.append(
            {
                "type": "rect",
                "version": "4.4.0",
                "left": int(rect["left"]),
                "top": int(rect["top"]),
                "width": int(rect["width"]),
                "height": int(rect["height"]),
                "fill": "rgba(255,255,255,1.0)",
                "stroke": None,
                "strokeWidth": 0,
                "originX": "left",
                "originY": "top",
                "angle": 0,
                "scaleX": 1,
                "scaleY": 1,
                "selectable": False,
                "evented": False,
            }
        )

    return {"version": "4.4.0", "objects": objects}


def _load_saved_mask_into_editor(*, selected_rel_path: str, saved_path: Path, preview_size: tuple[int, int]) -> None:
    with Image.open(saved_path) as saved_img:
        mask_img = saved_img.convert("L")
    if mask_img.size != preview_size:
        mask_img = mask_img.resize(preview_size, resample=Image.Resampling.NEAREST)
    canvas_state = _mask_image_to_canvas_state(mask_img)
    _set_canvas_state(selected_rel_path, canvas_state)
    _push_canvas_history(selected_rel_path, canvas_state)
    st.session_state[_canvas_rev_key(selected_rel_path)] = int(st.session_state.get(_canvas_rev_key(selected_rel_path)) or 0) + 1
    st.session_state[_canvas_auto_load_key(selected_rel_path)] = str(saved_path)


# Detector preview helpers
def _render_detector_preview(*, source_image: Image.Image, provider_payload: dict[str, Any], selected_rel_path: str) -> dict[str, Any]:
    from image.gui.common_ui import _ui_success, _ui_warning
    from image.provider_runtime import crop_detection_regions, draw_detection_preview, preview_local_adetailer_regions

    st.markdown("#### ADetailer detector preview")
    if not bool(provider_payload.get("local_adetailer_enabled", False)):
        _ui_info("Enable 'Enable local ADetailer pass' in the sidebar to see the detector preview.")
        return {"regions": [], "boxed": None, "crops": [], "preview": None}
    try:
        preview = preview_local_adetailer_regions(image=source_image, provider_payload=provider_payload)
    except Exception as exc:
        _ui_warning(f"Detector preview could not run: {_normalize_exc(exc)}")
        return {"regions": [], "boxed": None, "crops": [], "preview": None}
    regions = list(preview.get("regions") or [])
    meta_col, action_col = st.columns([1.2, 1.0])
    with meta_col:
        st.caption(f"Detector: {preview.get('detector') or '-'} | Regions: {preview.get('count') or 0}")
        for line in list(preview.get("logs") or []):
            st.caption(line)
    with action_col:
        if regions and st.button("Use preview boxes as manual regions", key=f"image_use_preview_boxes::{selected_rel_path}", width="stretch"):
            payload = [{"x": l, "y": t, "w": r - l, "h": b - t} for (l, t, r, b) in regions]
            raw_json = json.dumps(payload, ensure_ascii=False, indent=2)
            st.session_state["image_local_adetailer_detector"] = "manual_regions"
            st.session_state["image_local_adetailer_regions"] = raw_json
            _ui_success("Copied preview boxes into manual regions.")
    if not regions:
        _ui_warning("The detector did not find any region to refine on the selected image.")
        return {"regions": [], "boxed": None, "crops": [], "preview": preview}
    boxed = draw_detection_preview(image=source_image, regions=regions)
    st.image(boxed, caption="Detector preview boxes", width="stretch")
    crops = crop_detection_regions(image=source_image, regions=regions, padding_px=12)
    if crops:
        st.caption("Crop preview for each region so you can inspect where the detector locked on in more detail.")
        crop_cols = st.columns(min(3, max(1, len(crops))))
        for idx, crop in enumerate(crops):
            bbox = crop.get("bbox") or (0, 0, 0, 0)
            with crop_cols[idx % len(crop_cols)]:
                st.image(crop.get("image"), caption=f"#{crop.get('index')} | {bbox[0]},{bbox[1]} -> {bbox[2]},{bbox[3]}", width="stretch")
                st.caption(f"Crop size: {crop.get('size', ('-', '-'))[0]}x{crop.get('size', ('-', '-'))[1]}")
    with st.expander("Detector regions (JSON)", expanded=False):
        st.code(json.dumps([{"x": l, "y": t, "w": r - l, "h": b - t} for (l, t, r, b) in regions], ensure_ascii=False, indent=2), language="json")
    return {"regions": regions, "boxed": boxed, "crops": crops, "preview": preview}


def _render_adetailer_preview_for_entry(settings: dict[str, Any], prompt_dir: Path | None, entry: dict[str, Any], *, section_key: str) -> None:
    provider_payload = dict(settings.get("provider_payload") or {})
    source_path, source_label = _resolve_inpaint_source_for_entry(settings, prompt_dir, entry)
    if source_path is None or not source_path.is_file():
        _ui_info("Could not resolve a source image to build the detector preview for this prompt.")
        return
    with Image.open(source_path) as source_img:
        preview_source = source_img.convert("RGB")
    st.caption(f"Preview source: {source_label}")
    _render_detector_preview(source_image=preview_source, provider_payload=provider_payload, selected_rel_path=f"{section_key}::{entry['rel_path']}")

