from __future__ import annotations

import json

import streamlit as st

from common.gui.user_messages import (
    GuidanceAction,
    UserMessage,
    render_user_message,
)
from image.provider_runtime import (
    preload_local_provider,
)

from image.gui.main_panel import render_image_main_panel
from image.gui.settings import get_image_settings
from image.gui.state import ensure_session_defaults

APP_TITLE = "Render Image Workspace"


@st.cache_resource(show_spinner=False)
def _preload_local_pipeline_cached(settings_json: str) -> list[str]:
    settings = json.loads(settings_json)
    return preload_local_provider(settings)


def _maybe_preload_local_runtime(settings: dict[str, object]) -> None:
    if str(settings.get("provider") or "") != "stable_diffusion_local":
        return
    if not bool(settings.get("local_preload_model_on_startup", False)):
        return
    if not str(settings.get("local_model_id_or_path") or "").strip():
        return

    preload_settings = {
        "provider": settings.get("provider"),
        "local_model_id_or_path": settings.get("local_model_id_or_path"),
        "local_device": settings.get("local_device"),
        "local_dtype": settings.get("local_dtype"),
        "local_variant": settings.get("local_variant"),
        "local_use_safetensors": settings.get("local_use_safetensors"),
        "local_enable_attention_slicing": settings.get("local_enable_attention_slicing"),
        "local_enable_model_cpu_offload": settings.get("local_enable_model_cpu_offload"),
        "provider_payload": settings.get("provider_payload") or {},
    }
    settings_json = json.dumps(preload_settings, sort_keys=True)
    preload_key = f"image_preload_done::{settings_json}"
    is_first_visible = not bool(st.session_state.get(preload_key, False))
    try:
        if is_first_visible:
            with st.spinner("Preloading local SD runtime..."):
                logs = _preload_local_pipeline_cached(settings_json)
            st.session_state[preload_key] = True
            if logs:
                st.caption(" | ".join(logs[:3]))
        else:
            _preload_local_pipeline_cached(settings_json)
    except Exception as exc:
        render_user_message(
            UserMessage(
                level="info",
                title="Image local preload skipped",
                body=(
                    "The local image provider was not preloaded in this session. "
                    "Preload is optional; Generate or Test can still initialize the provider when needed."
                ),
                actions=(
                    GuidanceAction("Turn off startup preload if you do not need local warm-up."),
                    GuidanceAction("Open Doctor or run Test to check the local runtime."),
                ),
                technical_details=f"{exc.__class__.__name__}: {exc}",
            ),
            show_details=False,
        )


def render_image_workspace(*, embedded: bool = False) -> None:
    ensure_session_defaults()
    if not embedded:
        st.set_page_config(page_title=APP_TITLE, page_icon=":material/image:", layout="wide")
        st.title(APP_TITLE)
        st.caption("Generate cover and scene images from Story handoff using Stable Diffusion or ComfyUI.")
    else:
        st.subheader(APP_TITLE)
        st.caption("Story prompts -> images pipeline")

    settings = get_image_settings()
    _maybe_preload_local_runtime(settings)
    render_image_main_panel(settings, embedded=embedded)


def render_image_studio(*args, **kwargs):
    return render_image_workspace(*args, **kwargs)


def render_workspace(*args, **kwargs):
    return render_image_workspace(*args, **kwargs)


def render_studio(*args, **kwargs):
    return render_image_studio(*args, **kwargs)


def main(_args=None) -> int:
    render_image_workspace(embedded=False)
    return 0

