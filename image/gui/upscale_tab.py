from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image
import streamlit as st

from image.gui.user_messages import show_path_warning
from image.gui.state import (
    IMAGE_LAST_UPSCALE_OUTPUT_KEY,
    IMAGE_UPSCALE_RESAMPLE_KEY,
    IMAGE_UPSCALE_SCALE_KEY,
    IMAGE_UPSCALE_SOURCE_PATH_KEY,
    ensure_session_defaults,
)
from image.gui.upscale import _collect_upscale_source_candidates, _upscale_image_file

_IMAGE_TEMP_COVER_PATH_KEY = "image_temp_cover_path"
_IMAGE_TEMP_COVER_SOURCE_KEY = "image_temp_cover_source"
_IMAGE_UPSCALE_SOURCE_PENDING_KEY = "image_upscale_source_pending"
_IMAGE_UPSCALE_SOURCE_EDITOR_KEY = "image_upscale_source_editor"
_IMAGE_UPSCALE_OUTPUT_DIR_PENDING_KEY = "image_upscale_output_dir_pending"
_IMAGE_UPSCALE_OUTPUT_DIR_EDITOR_KEY = "image_upscale_output_dir_editor"


def _index_or_zero(options: list[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _normalize_exc(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


def _ui_error(message: str) -> None:
    st.error(message)


def _ui_success(message: str) -> None:
    st.success(message)


def _ui_info(message: str) -> None:
    st.info(message)


def _open_output_folder(path_value: str) -> None:
    path = Path(str(path_value or "")).expanduser()
    target = path if path.is_dir() else path.parent
    if not target.exists():
        _ui_error(f"Output folder does not exist: {target}")
        return
    try:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:
        _ui_error(f"Could not open folder: {_normalize_exc(exc)}")


def _copy_path_hint(path_value: str, *, key: str) -> None:
    path = str(path_value or "").strip()
    if not path:
        _ui_info("No output path yet.")
        return
    st.text_input("Copy output path", value=path, key=key, disabled=True)


def _set_temp_cover(path_value: str | Path, *, source_label: str = "") -> None:
    path = Path(path_value)
    st.session_state[_IMAGE_TEMP_COVER_PATH_KEY] = str(path)
    st.session_state[_IMAGE_TEMP_COVER_SOURCE_KEY] = source_label or path.name


def render_upscale_tab(settings: dict[str, Any]) -> None:
    ensure_session_defaults()
    st.subheader("Upscale")
    st.caption("Resize a source image and save a higher-resolution copy.")

    source_candidates = _collect_upscale_source_candidates(settings)
    stored_source = str(st.session_state.get(IMAGE_UPSCALE_SOURCE_PATH_KEY) or "").strip()
    pending_source = str(st.session_state.get(_IMAGE_UPSCALE_SOURCE_PENDING_KEY) or "").strip()
    if pending_source:
        st.session_state[IMAGE_UPSCALE_SOURCE_PATH_KEY] = pending_source
        st.session_state[_IMAGE_UPSCALE_SOURCE_EDITOR_KEY] = pending_source
        st.session_state[_IMAGE_UPSCALE_SOURCE_PENDING_KEY] = ""
        stored_source = pending_source
    if stored_source and not Path(stored_source).expanduser().is_file() and source_candidates:
        stored_source = str(source_candidates[0][1])
        st.session_state[IMAGE_UPSCALE_SOURCE_PATH_KEY] = stored_source
        st.session_state[_IMAGE_UPSCALE_SOURCE_EDITOR_KEY] = stored_source
    source_path_value = stored_source
    selected_source_label = ""

    if st.button("Refresh sources", key="image_upscale_refresh_sources", width="stretch"):
        st.rerun()

    source_path_value = st.text_input(
        "Image path to upscale",
        value=str(st.session_state.get(_IMAGE_UPSCALE_SOURCE_EDITOR_KEY) or source_path_value),
        key=_IMAGE_UPSCALE_SOURCE_EDITOR_KEY,
        help="Pick an image file from the available sources or paste any local image path.",
    ).strip()
    source_path = Path(source_path_value).expanduser() if source_path_value else None
    st.session_state[IMAGE_UPSCALE_SOURCE_PATH_KEY] = source_path_value

    if source_candidates:
        with st.expander("Available source images", expanded=not bool(source_path_value)):
            source_labels = [label for label, _ in source_candidates]
            source_paths = [str(path) for _, path in source_candidates]
            if source_path_value and source_path_value in source_paths:
                selected_index = source_paths.index(source_path_value)
            elif stored_source and stored_source in source_paths:
                selected_index = source_paths.index(stored_source)
            else:
                selected_index = 0
            selected_source_label = source_labels[selected_index]
            selected_source = st.selectbox(
                "Choose a source image",
                options=source_paths,
                index=selected_index,
                format_func=lambda value: next((f"{label} | {value}" for label, candidate in source_candidates if str(candidate) == value), value),
                key="image_upscale_source_picker",
            )
            st.caption(f"Selected source: {selected_source_label}")
            if st.button("Use selected source", key="image_upscale_use_selected", width="stretch"):
                st.session_state[_IMAGE_UPSCALE_SOURCE_PENDING_KEY] = selected_source
                st.session_state[_IMAGE_UPSCALE_OUTPUT_DIR_PENDING_KEY] = str(Path(selected_source).expanduser().parent / "upscaled")
                st.rerun()
    else:
        _ui_info("No image source is available yet. Run Generate or paste a path to upscale.")

    if source_path is not None and source_path.is_file():
        with Image.open(source_path) as source_img:
            source_preview = source_img.convert("RGB")
        st.image(source_preview, caption=f"Source preview | {source_path.name}", width="stretch")
    else:
        show_path_warning(
            "image source",
            path_value=source_path_value,
            actions=["Pick a file from Available source images.", "Paste the path to a valid PNG/JPG/WebP image."],
        )

    scale_mode = st.selectbox(
        "Upscale factor",
        options=["2x", "4x", "Custom"],
        index=_index_or_zero(["2x", "4x", "Custom"], "2x" if float(st.session_state.get(IMAGE_UPSCALE_SCALE_KEY) or 2.0) == 2.0 else "4x" if float(st.session_state.get(IMAGE_UPSCALE_SCALE_KEY) or 2.0) == 4.0 else "Custom"),
        key="image_upscale_scale_mode",
    )
    if scale_mode == "Custom":
        scale_factor = float(st.session_state.get(IMAGE_UPSCALE_SCALE_KEY) or 2.0)
        scale_factor = float(st.number_input("Custom scale", min_value=1.1, max_value=8.0, value=scale_factor, step=0.1, key=IMAGE_UPSCALE_SCALE_KEY))
    else:
        scale_factor = 2.0 if scale_mode == "2x" else 4.0
        st.session_state[IMAGE_UPSCALE_SCALE_KEY] = scale_factor

    resample_options = ["lanczos", "bicubic", "bilinear", "nearest"]
    resample_value = st.selectbox(
        "Resize method",
        options=resample_options,
        index=_index_or_zero(resample_options, str(st.session_state.get(IMAGE_UPSCALE_RESAMPLE_KEY) or "lanczos")),
        key=IMAGE_UPSCALE_RESAMPLE_KEY,
        help="Lanczos usually gives the sharpest results for a simple resize-based upscale.",
    )

    pending_output_dir = str(st.session_state.get(_IMAGE_UPSCALE_OUTPUT_DIR_PENDING_KEY) or "").strip()
    if pending_output_dir:
        st.session_state["image_upscale_output_dir"] = pending_output_dir
        st.session_state[_IMAGE_UPSCALE_OUTPUT_DIR_EDITOR_KEY] = pending_output_dir
        st.session_state[_IMAGE_UPSCALE_OUTPUT_DIR_PENDING_KEY] = ""

    output_dir_default = str(st.session_state.get("image_upscale_output_dir") or "")
    if not output_dir_default and source_path is not None and source_path.is_file():
        output_dir_default = str(source_path.parent / "upscaled")
    output_dir_value = st.text_input(
        "Output directory (optional)",
        value=str(st.session_state.get(_IMAGE_UPSCALE_OUTPUT_DIR_EDITOR_KEY) or output_dir_default),
        key=_IMAGE_UPSCALE_OUTPUT_DIR_EDITOR_KEY,
        help="Leave empty to save next to the source image in an upscaled/ folder.",
    ).strip()
    st.session_state["image_upscale_output_dir"] = output_dir_value

    current_upscale_output = str(st.session_state.get(IMAGE_LAST_UPSCALE_OUTPUT_KEY) or "").strip()
    if current_upscale_output and Path(current_upscale_output).is_file():
        st.caption(f"Last upscale output: {current_upscale_output}")
        try:
            with Image.open(current_upscale_output) as preview_img:
                st.image(preview_img.convert("RGB"), caption=Path(current_upscale_output).name, width="stretch")
        except Exception:
            pass

    action_col, open_col, copy_col = st.columns([1.2, 0.8, 0.8])
    with action_col:
        upscale_clicked = st.button("Upscale image", type="primary", width="stretch", disabled=not (source_path is not None and source_path.is_file()))
    with open_col:
        if st.button("Open output folder", width="stretch", disabled=not bool(current_upscale_output)):
            _open_output_folder(current_upscale_output)
    with copy_col:
        _copy_path_hint(current_upscale_output, key="image_upscale_copy_output")

    if upscale_clicked:
        if source_path is None or not source_path.is_file():
            _ui_error("Please choose a valid source image before upscaling.")
            return
        try:
            output_path, upscaled_img = _upscale_image_file(
                source_path,
                scale=scale_factor,
                resample=resample_value,
                output_dir_value=output_dir_value,
            )
            st.session_state[IMAGE_LAST_UPSCALE_OUTPUT_KEY] = str(output_path)
            _ui_success(f"Upscaled image saved: {output_path}")
            st.image(upscaled_img, caption=f"Upscaled x{scale_factor:g}", width="stretch")
            st.caption(str(output_path))
            if st.button("Set as temporary cover", key="image_upscale_set_temp_cover", width="stretch"):
                _set_temp_cover(output_path, source_label=f"upscale | {output_path.name}")
                st.rerun()
        except Exception as exc:
            _ui_error(f"Could not upscale image: {_normalize_exc(exc)}")

