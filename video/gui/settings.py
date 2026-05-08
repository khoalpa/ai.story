from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import streamlit as st

from video.asset_profile_utils import (
    list_asset_profiles,
    pick_default_asset_profile,
    resolve_profile_defaults,
)
from video.config import DEFAULT_PROFILE_ROOT
from video.error_handling import USER_FACING_EXCEPTIONS, format_user_facing_error
from video.runtime_tools import collect_runtime_diagnostics
from video.providers.base import VideoProviderDescriptor
from video.providers.registry import get_video_provider_descriptors, normalize_video_provider
from common.gui.diagnostics_blocks import render_runtime_diagnostics_block
from common.gui.sidebar_sections import SidebarSection
from common.gui.user_messages import show_path_warning


def _render_dependency_diagnostics(provider: VideoProviderDescriptor, settings: dict[str, Any]) -> None:
    collector = provider.collect_runtime_diagnostics
    report = collector(settings) if collector is not None else collect_runtime_diagnostics()
    render_runtime_diagnostics_block(report, serializer=lambda info: info.as_dict())


def _safe_ui_call(name: str, *args, **kwargs):
    fn = getattr(st, name, None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def get_video_settings() -> dict[str, Any]:
    with st.sidebar:
        st.header(SidebarSection.PROFILES)
        profile_root = st.text_input("Profile root", value=str(DEFAULT_PROFILE_ROOT))
        profiles = list_asset_profiles(profile_root)
        profile_options = ["", *profiles]
        default_profile = pick_default_asset_profile(profiles)
        default_index = profile_options.index(default_profile) if default_profile else 0
        asset_profile = st.selectbox(
            "Asset profile",
            options=profile_options,
            index=default_index,
            help="Leave empty if you do not want to use a profile",
        )

        defaults: dict[str, Optional[Path]] = {
            "profile_dir": None,
            "cover": None,
            "scenes_dir": None,
        }
        profile_error: Optional[str] = None
        if asset_profile:
            try:
                defaults = resolve_profile_defaults(profile_root, asset_profile)
            except USER_FACING_EXCEPTIONS as exc:
                profile_error = format_user_facing_error(exc)
        if profile_error:
            show_path_warning("asset profile", path_value=asset_profile, actions=[profile_error, "Check the profile root again or choose another profile."])
        elif asset_profile and defaults.get("profile_dir") is not None:
            _safe_ui_call("caption", f"Profile dir: {defaults['profile_dir']}")

        st.header(SidebarSection.PROVIDER)
        provider_descriptors = get_video_provider_descriptors()
        provider_options = list(provider_descriptors)
        selected_provider = normalize_video_provider(st.session_state.get("video_provider"))
        if selected_provider not in provider_options:
            selected_provider = provider_options[0]
        selected_provider = st.selectbox(
            "Video Provider",
            options=provider_options,
            index=provider_options.index(selected_provider),
            key="video_provider",
            format_func=lambda provider_id: provider_descriptors[provider_id].label,
        )
        provider_descriptor = provider_descriptors[selected_provider]
        st.caption(provider_descriptor.description)
        provider_settings = provider_descriptor.render_sidebar()
        provider_values = provider_settings.as_dict()

        st.header(SidebarSection.INPUTS_OUTPUTS)
        input_root = st.text_input("Input root", value="output")
        output_dir = st.text_input("Output directory", value="output")

        st.header(SidebarSection.RENDER)
        mode = st.radio("Mode", options=["static", "slideshow"], index=0, horizontal=True)
        aspect = st.selectbox("Aspect", options=["9x16", "16x9"], index=0)
        duration_per_image = st.number_input(
            "Duration per image (slideshow)", min_value=1.0, value=60.0, step=1.0
        )

        st.header(SidebarSection.RUNTIME)
        _render_dependency_diagnostics(provider_descriptor, provider_values)

    return {
        **provider_values,
        "profile_root": profile_root,
        "input_root": input_root,
        "output_dir": output_dir,
        "profiles": profiles,
        "asset_profile": asset_profile,
        "defaults": defaults,
        "profile_error": profile_error,
        "mode": mode,
        "aspect": aspect,
        "duration_per_image": float(duration_per_image),
    }


def render_settings_sidebar() -> dict[str, Any]:
    return get_video_settings()


def get_settings() -> dict[str, Any]:
    return get_video_settings()


def render_settings() -> dict[str, Any]:
    return get_video_settings()


def render_sidebar() -> dict[str, Any]:
    return render_settings_sidebar()
