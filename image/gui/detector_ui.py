from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image
import streamlit as st

from image.gui.common_ui import _normalize_exc, _ui_info, _ui_success, _ui_warning
from image.provider_runtime import (
    crop_detection_regions,
    draw_detection_preview,
    preview_local_adetailer_regions,
)


def _render_detector_preview(*, source_image: Image.Image, provider_payload: dict[str, Any], selected_rel_path: str) -> dict[str, Any]:
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
    from image.gui.inpaint_utils import _resolve_inpaint_source_for_entry

    provider_payload = dict(settings.get("provider_payload") or {})
    source_path, source_label = _resolve_inpaint_source_for_entry(settings, prompt_dir, entry)
    if source_path is None or not source_path.is_file():
        _ui_info("Could not resolve a source image to build the detector preview for this prompt.")
        return
    with Image.open(source_path) as source_img:
        preview_source = source_img.convert("RGB")
    st.caption(f"Preview source: {source_label}")
    _render_detector_preview(source_image=preview_source, provider_payload=provider_payload, selected_rel_path=f"{section_key}::{entry['rel_path']}")

