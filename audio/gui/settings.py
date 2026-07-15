from __future__ import annotations

import streamlit as st

from audio.gui.sidebar_sections import SidebarSection
from audio.gui.user_messages import UserMessage, render_user_message
from audio.model_store import list_local_models, list_local_targets, provider_models_dir, provider_target_dir
from audio.app_config import AppConfig
from audio.profile_config import ProfileConfig
from audio.services.render_runtime import DEFAULT_PROFILE_ROOT
from audio.runtime_checks import collect_runtime_diagnostics_for_settings, runtime_diagnostics_to_lines
from audio.tts_provider import get_tts_provider_choices, get_tts_provider_descriptor
from audio.providers.vieneu import BACKEND_OPTIONS as VIENEU_BACKEND_OPTIONS
from audio.providers.vieneu import CORE_OPTIONS as VIENEU_CORE_OPTIONS
from audio.providers.vieneu import MODE_OPTIONS as VIENEU_MODE_OPTIONS
from audio.providers.vieneu import RENDER_AUDIO_OPTIONS as VIENEU_RENDER_AUDIO_OPTIONS
from audio.voice_catalog import find_local_voice_notice, get_voice_choices, resolve_voice_selection
from audio.adapters.tts_core import DEFAULT_VIENEU_API_BASE, adopt_vieneu_cached_codec, adopt_vieneu_cached_distilhubert, get_default_vieneu_local_target, get_default_vieneu_model_name, get_first_vieneu_local_model, get_vieneu_cached_codec_snapshot, get_vieneu_cached_distilhubert_snapshot, is_vieneu_mode_model_compatible, list_vieneu_local_models, resolve_vieneu_model_name
from .state import (
    VOICE_EN_FEMALE_SPEED_KEY,
    VOICE_EN_MALE_SPEED_KEY,
    VOICE_EN_NARRATOR_SPEED_KEY,
    VOICE_FEMALE_SPEED_KEY,
    VOICE_MALE_SPEED_KEY,
    VOICE_NARRATOR_SPEED_KEY,
    VOICE_SPEED_DEFAULTS,
)
from .service import (
    format_runtime_error,
    get_vieneu_runtime_model_details,
    normalize_vieneu_core,
    probe_vieneu_core_connection_from_settings,
    refresh_vieneu_voices_from_settings,
    resolve_vieneu_runtime_mode,
    resolve_vieneu_ui_mode,
)

from .config_bundle import GuiConfigBundle
from .constants import DEFAULT_STORE_PATH
from .helpers import (
    find_binary,
    list_asset_profiles,
    list_profile_bgm_files,
    read_profile_bgm_config,
    read_profile_manifest,
)


def _radio(label: str, options: list[str], *, index: int = 0, **kwargs):
    radio_fn = getattr(st, "radio", None)
    if callable(radio_fn):
        return radio_fn(label, options, index=index, **kwargs)
    return options[index]


def _expander(label: str, *, expanded: bool = False):
    expander_fn = getattr(st, "expander", None)
    if callable(expander_fn):
        return expander_fn(label, expanded=expanded)

    class _NoopContext:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
    return _NoopContext()


def _normalize_vieneu_device_choice(value: object) -> str:
    normalized = str(value or "auto").strip().lower().replace("-", "_")
    if normalized == "cpu":
        return "cpu"
    if normalized in {"auto", "cuda", "gpu", "cuda:0", "cuda0", "default", "prefer_gpu"}:
        return "auto"
    return "auto"


def _normalize_vieneu_backend_choice(value: object) -> str:
    normalized = str(value or "auto").strip().lower().replace("-", "_")
    if normalized in {"auto", "native", "lmdeploy"}:
        return normalized
    return "auto"







def _render_audio_local_model_picker(*, provider_id: str, current_model: str, mode: str) -> tuple[str, str]:
    target_dir = provider_target_dir("audio", provider_id, __file__)
    local_targets = list(list_vieneu_local_models(mode=mode, max_depth=4)) if provider_id == "vieneu" else list_local_targets("audio", __file__, provider_id=provider_id, max_depth=4)
    options = ["(manual)", *local_targets]
    key = f"audio_local_model_target::{provider_id}"

    def _format_local_target_label(value: str) -> str:
        if value == "(manual)":
            return "(manual)"
        normalized = str(value or "").strip().replace("\\", "/").rstrip("/")
        name = normalized.rsplit("/", 1)[-1] if normalized else str(value or "").strip()
        if provider_id == "vieneu":
            if mode == "standard":
                family = "standard"
            elif mode in {"turbo", "fast", "cuda", "turbo_gpu", "xpu"}:
                family = "turbo"
            else:
                family = mode
            return f"{family} | {name}"
        return name

    request_key = f"use_first_local_model_request::{provider_id}"
    if st.session_state.pop(request_key, False):
        first_local = get_first_vieneu_local_model(mode=mode) if provider_id == "vieneu" else (local_targets[0] if local_targets else "")
        if first_local:
            st.session_state[key] = first_local
            if provider_id == "vieneu":
                st.session_state["vieneu_model_name"] = first_local
        else:
            st.session_state["audio_provider_action_status"] = ("warning", f"No suitable local model was found for mode={mode} in {target_dir}")

    selected = str(st.session_state.get(key) or "(manual)")
    normalized_current = str(current_model or "").strip().replace("\\", "/")
    available_targets = {str(item).strip().replace("\\", "/") for item in local_targets}
    if normalized_current and normalized_current in available_targets and selected == "(manual)":
        selected = normalized_current
        st.session_state[key] = selected
    if selected not in options:
        selected = "(manual)"
        st.session_state[key] = selected

    selected = st.selectbox(
        "Local model target",
        options=options,
        index=options.index(selected),
        key=key,
        format_func=_format_local_target_label,
        help="Scan from audio/models/vieneu/. Use this dropdown when the model already exists in the project.",
    )
    st.caption(f"Update target: {target_dir}")
    if local_targets:
        preview_targets = ", ".join(_format_local_target_label(item) for item in local_targets[:6])
        st.caption(f"Scanned local targets ({mode}): {preview_targets}{' ...' if len(local_targets) > 6 else ''}")
    else:
        st.caption(f"No suitable local model was found for mode={mode} in {target_dir}")

    def _request_use_first_local_model() -> None:
        st.session_state[request_key] = True

    col_manual, col_local = st.columns([3, 1])
    with col_manual:
        if selected != "(manual)":
            st.session_state["vieneu_model_name"] = selected
        else:
            st.session_state.setdefault("vieneu_model_name", current_model)
        manual_value = st.text_input(
            "VieNeu model/repo",
            key="vieneu_model_name",
            help="turbo -> Turbo/GGUF model; standard -> Standard/PyTorch-compatible model. With remote API, this model name is sent to the server.",
        )
    with col_local:
        st.button(
            "Use first local model",
            width="stretch",
            key=f"use_first_local_model::{provider_id}",
            on_click=_request_use_first_local_model,
        )
    return (selected if selected != "(manual)" else str(manual_value).strip()), str(target_dir)


def _resolve_vieneu_mode_default_model(*, core: str, mode: str, current_model: str) -> str:
    clean_current = str(current_model or "").strip()
    repo_default = get_default_vieneu_model_name(mode)
    local_default = get_default_vieneu_local_target(mode)
    local_default_path = provider_target_dir("audio", "vieneu", __file__) / local_default
    first_local = get_first_vieneu_local_model(mode=mode)
    local_placeholders = {
        get_default_vieneu_local_target("standard"),
    }
    repo_placeholders = {
        get_default_vieneu_model_name("standard"),
    }
    if core == "local":
        preferred_local = local_default if local_default_path.exists() else str(first_local or "").strip()
        if preferred_local and (not clean_current or clean_current in repo_placeholders or clean_current in local_placeholders):
            return preferred_local
    if not clean_current or clean_current == get_default_vieneu_model_name("standard"):
        return repo_default
    return clean_current


def _render_audio_provider_status() -> None:
    payload = st.session_state.get("audio_provider_action_status")
    if not isinstance(payload, tuple) or len(payload) != 2:
        return
    level, message = payload
    render_user_message(UserMessage(level=str(level or "info"), title="Audio provider", body=str(message or "")))


def _format_voice_speed_percent(value: object) -> str:
    try:
        speed = int(value)
    except (TypeError, ValueError):
        speed = 0
    if speed == 0:
        return "0%"
    return f"{speed:+d}%"


def _render_voice_speed_slider(*, key: str, default_value: int) -> int:
    current_value = st.session_state.get(key)
    if current_value is None:
        current_value = default_value
    try:
        current_int = int(current_value)
    except (TypeError, ValueError):
        current_int = int(default_value)
    current_int = max(-100, min(100, current_int))
    st.session_state[key] = current_int
    col_label, col_slider = st.columns([1.6, 5.9], gap="small")
    with col_label:
        st.markdown(
            "<div style='padding-top: 0.42rem; font-size: 0.94rem; line-height: 1.15; white-space: nowrap;'>Speed</div>",
            unsafe_allow_html=True,
        )
    with col_slider:
        new_value = int(
            st.slider(
                " ",
                min_value=-100,
                max_value=100,
                value=current_int,
                key=key,
                label_visibility="collapsed",
            )
        )

    return new_value

def _voice_selectbox(
    label: str,
    *,
    provider: str,
    lang: str,
    role: str,
    current_value: str,
    fallback: str,
    key: str,
    allow_custom_input: bool = False,
) -> str:
    choices = list(get_voice_choices(tts_provider=provider, lang=lang, role=role))
    values = [item.value for item in choices]
    labels = {item.value: item.label for item in choices}
    selected = resolve_voice_selection(current_value, tts_provider=provider, lang=lang, role=role, fallback=fallback)
    if not values:
        return st.text_input(label, value=current_value or fallback, key=f"{key}_input")

    resolved_default = selected if selected in values else values[0]
    signature_key = f"{key}__options_signature"
    default_key = f"{key}__resolved_default"

    prior_selected = str(st.session_state.get(key) or "").strip()
    prior_default = str(st.session_state.get(default_key) or "").strip()
    options_signature = "|".join(values)
    options_changed = str(st.session_state.get(signature_key) or "") != options_signature

    if key not in st.session_state:
        st.session_state[key] = resolved_default
    elif prior_selected and prior_selected not in values:
        st.session_state[key] = resolve_voice_selection(
            prior_selected,
            tts_provider=provider,
            lang=lang,
            role=role,
            fallback=resolved_default,
        )
        if str(st.session_state.get(key) or "").strip() not in values:
            st.session_state[key] = resolved_default
    elif prior_selected == prior_default and prior_default != resolved_default:
        st.session_state[key] = resolved_default
    elif options_changed and prior_selected == prior_default:
        st.session_state[key] = resolved_default

    if str(st.session_state.get(key) or "").strip() not in values:
        st.session_state[key] = resolved_default

    st.session_state[signature_key] = options_signature
    st.session_state[default_key] = resolved_default

    selected_value = st.selectbox(
        label,
        options=values,
        format_func=lambda value: labels.get(value, value),
        key=key,
    )
    if not allow_custom_input:
        st.session_state.pop(f"{key}_override", None)
        st.session_state.pop(f"{key}_input", None)
        return str(selected_value).strip()
    override = st.text_input(
        f"{label} override",
        value="" if selected_value in values else (current_value or ""),
        help="Leave empty to use the dropdown value. Enter a custom value only if you need a voice ID/name outside the list.",
        key=f"{key}_override",
    )
    return str(override or selected_value).strip()


def _render_voice_selector_block(*, provider: str, profile_defaults: dict, advanced: bool) -> tuple[str, str, str, str, str, str]:
    defaults = dict(profile_defaults or {})
    if advanced:
        st.header("Voice defaults")
    else:
        st.subheader("Voice defaults")
        st.caption("The voice list updates automatically with the selected TTS provider. With VieNeu TTS core, preset choices appear when the vieneu SDK is installed.")

    voice_narrator = _voice_selectbox(
        "VI narrator",
        provider=provider,
        lang="vi",
        role="narrator",
        current_value=str(defaults["voice_narrator"]),
        fallback=str(defaults["voice_narrator"]),
        key="voice_vi_narrator",
        allow_custom_input=False,
    )
    _render_voice_speed_slider(
        key=VOICE_NARRATOR_SPEED_KEY,
        default_value=int(defaults.get(VOICE_NARRATOR_SPEED_KEY) or VOICE_SPEED_DEFAULTS[VOICE_NARRATOR_SPEED_KEY]),
    )
    voice_female = _voice_selectbox(
        "VI female",
        provider=provider,
        lang="vi",
        role="female",
        current_value=str(defaults["voice_female"]),
        fallback=str(defaults["voice_female"]),
        key="voice_vi_female",
        allow_custom_input=False,
    )
    _render_voice_speed_slider(
        key=VOICE_FEMALE_SPEED_KEY,
        default_value=int(defaults.get(VOICE_FEMALE_SPEED_KEY) or VOICE_SPEED_DEFAULTS[VOICE_FEMALE_SPEED_KEY]),
    )
    voice_male = _voice_selectbox(
        "VI male",
        provider=provider,
        lang="vi",
        role="male",
        current_value=str(defaults["voice_male"]),
        fallback=str(defaults["voice_male"]),
        key="voice_vi_male",
        allow_custom_input=False,
    )
    _render_voice_speed_slider(
        key=VOICE_MALE_SPEED_KEY,
        default_value=int(defaults.get(VOICE_MALE_SPEED_KEY) or VOICE_SPEED_DEFAULTS[VOICE_MALE_SPEED_KEY]),
    )
    voice_en_narrator = _voice_selectbox(
        "EN narrator",
        provider=provider,
        lang="en",
        role="narrator",
        current_value=str(defaults["voice_en_narrator"]),
        fallback=str(defaults["voice_en_narrator"]),
        key="voice_en_narrator_key",
        allow_custom_input=False,
    )
    _render_voice_speed_slider(
        key=VOICE_EN_NARRATOR_SPEED_KEY,
        default_value=int(defaults.get(VOICE_EN_NARRATOR_SPEED_KEY) or VOICE_SPEED_DEFAULTS[VOICE_EN_NARRATOR_SPEED_KEY]),
    )
    voice_en_female = _voice_selectbox(
        "EN female",
        provider=provider,
        lang="en",
        role="female",
        current_value=str(defaults["voice_en_female"]),
        fallback=str(defaults["voice_en_female"]),
        key="voice_en_female_key",
        allow_custom_input=False,
    )
    _render_voice_speed_slider(
        key=VOICE_EN_FEMALE_SPEED_KEY,
        default_value=int(defaults.get(VOICE_EN_FEMALE_SPEED_KEY) or VOICE_SPEED_DEFAULTS[VOICE_EN_FEMALE_SPEED_KEY]),
    )
    voice_en_male = _voice_selectbox(
        "EN male",
        provider=provider,
        lang="en",
        role="male",
        current_value=str(defaults["voice_en_male"]),
        fallback=str(defaults["voice_en_male"]),
        key="voice_en_male_key",
        allow_custom_input=False,
    )
    _render_voice_speed_slider(
        key=VOICE_EN_MALE_SPEED_KEY,
        default_value=int(defaults.get(VOICE_EN_MALE_SPEED_KEY) or VOICE_SPEED_DEFAULTS[VOICE_EN_MALE_SPEED_KEY]),
    )
    return (
        voice_narrator,
        voice_female,
        voice_male,
        voice_en_narrator,
        voice_en_female,
        voice_en_male,
    )


def _build_vieneu_runtime_settings(
    *,
    core: str,
    mode: str,
    api_base: str,
    model_name: str,
    local_update_target: str = "",
) -> dict[str, object]:
    return {
        "vieneu_core": core,
        "vieneu_mode": mode,
        "vieneu_api_base": api_base,
        "vieneu_model_name": model_name,
        "vieneu_device": st.session_state.get("vieneu_device"),
        "vieneu_backend": st.session_state.get("vieneu_backend"),
        "local_update_target": local_update_target,
    }


def _build_vieneu_persisted_settings(
    *,
    core: str,
    mode: str,
    api_base: str,
    model_name: str,
    local_update_target: str = "",
) -> dict[str, object]:
    return {
        "vieneu_core": core,
        "vieneu_mode": resolve_vieneu_runtime_mode(core, mode, st.session_state.get("vieneu_device")),
        "vieneu_api_base": api_base,
        "vieneu_model_name": model_name,
        "vieneu_device": st.session_state.get("vieneu_device"),
        "vieneu_backend": st.session_state.get("vieneu_backend"),
        "local_update_target": local_update_target,
    }


def render_settings_sidebar() -> GuiConfigBundle:
    app_defaults = AppConfig.defaults()
    profile_defaults = ProfileConfig.defaults()

    with st.sidebar:
        st.header(SidebarSection.PROFILES)
        profile_root = st.text_input("Profile root", value=str(DEFAULT_PROFILE_ROOT))
        discovered_profiles = list_asset_profiles(profile_root)
        profile_options = ["", *discovered_profiles]
        default_profile = profile_defaults.get("asset_profile") or ""
        if default_profile not in profile_options:
            default_profile = "demo" if "demo" in profile_options else ""
        asset_profile = st.selectbox(
            "Profile preset",
            options=profile_options,
            index=profile_options.index(default_profile) if default_profile in profile_options else 0,
            help="Leave empty if you do not want to use a profile",
        )

        manifest = read_profile_manifest(profile_root, asset_profile)
        if manifest:
            st.caption(f"Profile manifest: {manifest.get('profile_id', asset_profile)}")
            manifest_voices = manifest.get("voices")
            if isinstance(manifest_voices, dict):
                for key in (
                    "voice_narrator",
                    "voice_female",
                    "voice_male",
                    "voice_en_narrator",
                    "voice_en_female",
                    "voice_en_male",
                    "vi_narrator",
                    "vi_female",
                    "vi_male",
                    "en_narrator",
                    "en_female",
                    "en_male",
                ):
                    value = manifest_voices.get(key)
                    if isinstance(value, str) and value.strip():
                        canonical_key = {
                            "vi_narrator": "voice_narrator",
                            "vi_female": "voice_female",
                            "vi_male": "voice_male",
                            "en_narrator": "voice_en_narrator",
                            "en_female": "voice_en_female",
                            "en_male": "voice_en_male",
                        }.get(key, key)
                        profile_defaults[canonical_key] = value.strip()

        bgm_files = list_profile_bgm_files(profile_root, asset_profile) if asset_profile else []
        bgm_options = ["", *bgm_files] if bgm_files else [""]
        bgm_default = profile_defaults.get("bgm") or ("bgm_lofi.mp3" if "bgm_lofi.mp3" in bgm_options else "")
        bgm = (
            st.selectbox("BGM fallback", bgm_options, index=bgm_options.index(bgm_default) if bgm_default in bgm_options else 0)
            if bgm_files else st.text_input("BGM fallback", value=bgm_default)
        )
        bgmdir = st.text_input("BGM dir", value=str(profile_defaults["bgmdir"]))
        bgm_config = st.text_input(
            "BGM config",
            value="bgm_config.json" if asset_profile and read_profile_bgm_config(profile_root, asset_profile) else (profile_defaults.get("bgm_config") or ""),
        )
        abbr_map = st.text_input("Abbreviation map", value=str(profile_defaults["abbr_map"]))

        st.header(SidebarSection.PROVIDER)
        st.session_state.setdefault(
            "vieneu_device",
            _normalize_vieneu_device_choice(profile_defaults.get("vieneu_device") or app_defaults.get("vieneu_device") or "auto"),
        )
        st.session_state.setdefault(
            "vieneu_backend",
            _normalize_vieneu_backend_choice(profile_defaults.get("vieneu_backend") or app_defaults.get("vieneu_backend") or "auto"),
        )
        tts_provider_options = get_tts_provider_choices()
        default_tts = str(profile_defaults.get("tts_provider") or app_defaults["tts_provider"])
        tts_provider = st.selectbox(
            "TTS provider",
            tts_provider_options,
            index=tts_provider_options.index(default_tts) if default_tts in tts_provider_options else 0,
            help="Provider list is discovered from audio/providers.",
        )
        st.caption(get_tts_provider_descriptor(tts_provider).description)
        local_vi_notice = find_local_voice_notice(tts_provider=tts_provider, lang="vi")
        if local_vi_notice:
            render_user_message(UserMessage(level="warning", title="Local voice notice", body=local_vi_notice))
        st.session_state["vieneu_device"] = _normalize_vieneu_device_choice(st.session_state.get("vieneu_device"))
        st.selectbox(
            "Render audio",
            list(VIENEU_RENDER_AUDIO_OPTIONS),
            index=0 if _normalize_vieneu_device_choice(st.session_state.get("vieneu_device")) == "auto" else 1,
            key="vieneu_device",
            help="Choose the device used by VieNeu rendering and preview. auto prefers GPU when available, otherwise CPU.",
        )
        st.session_state.setdefault("vieneu_core", "local")
        st.session_state.setdefault("vieneu_mode", "standard" if str(profile_defaults.get("vieneu_mode") or app_defaults.get("vieneu_mode") or "standard") == "standard" else "standard")
        st.session_state.setdefault("vieneu_api_base", str(profile_defaults.get("vieneu_api_base") or app_defaults.get("vieneu_api_base") or ""))
        st.session_state.setdefault(
            "vieneu_model_name",
            _resolve_vieneu_mode_default_model(
                core=str(st.session_state.get("vieneu_core") or "local"),
                mode=str(st.session_state.get("vieneu_mode") or "standard"),
                current_model=str(profile_defaults.get("vieneu_model_name") or app_defaults.get("vieneu_model_name") or resolve_vieneu_model_name("", st.session_state.get("vieneu_mode") or "standard")),
            ),
        )
        st.session_state.setdefault(VOICE_NARRATOR_SPEED_KEY, int(profile_defaults.get(VOICE_NARRATOR_SPEED_KEY) or app_defaults.get(VOICE_NARRATOR_SPEED_KEY) or 25))
        st.session_state.setdefault(VOICE_FEMALE_SPEED_KEY, int(profile_defaults.get(VOICE_FEMALE_SPEED_KEY) or app_defaults.get(VOICE_FEMALE_SPEED_KEY) or 25))
        st.session_state.setdefault(VOICE_MALE_SPEED_KEY, int(profile_defaults.get(VOICE_MALE_SPEED_KEY) or app_defaults.get(VOICE_MALE_SPEED_KEY) or 25))
        st.session_state.setdefault(VOICE_EN_NARRATOR_SPEED_KEY, int(profile_defaults.get(VOICE_EN_NARRATOR_SPEED_KEY) or app_defaults.get(VOICE_EN_NARRATOR_SPEED_KEY) or 25))
        st.session_state.setdefault(VOICE_EN_FEMALE_SPEED_KEY, int(profile_defaults.get(VOICE_EN_FEMALE_SPEED_KEY) or app_defaults.get(VOICE_EN_FEMALE_SPEED_KEY) or 25))
        st.session_state.setdefault(VOICE_EN_MALE_SPEED_KEY, int(profile_defaults.get(VOICE_EN_MALE_SPEED_KEY) or app_defaults.get(VOICE_EN_MALE_SPEED_KEY) or 25))
        st.session_state.setdefault("vieneu_preview_temperature", float(profile_defaults.get("vieneu_preview_temperature") or app_defaults.get("vieneu_preview_temperature") or 0.6))
        st.session_state.setdefault("vieneu_preview_max_chars_chunk", int(profile_defaults.get("vieneu_preview_max_chars_chunk") or app_defaults.get("vieneu_preview_max_chars_chunk") or 160))
        st.session_state.setdefault("vieneu_preview_use_batch", bool(profile_defaults.get("vieneu_preview_use_batch") or app_defaults.get("vieneu_preview_use_batch") or False))
        st.session_state.setdefault("vieneu_preview_max_batch_size_run", int(profile_defaults.get("vieneu_preview_max_batch_size_run") or app_defaults.get("vieneu_preview_max_batch_size_run") or 1))
        st.session_state.setdefault("vieneu_preview_text_max_len", int(profile_defaults.get("vieneu_preview_text_max_len") or app_defaults.get("vieneu_preview_text_max_len") or 100))
        st.session_state.setdefault("vieneu_render_temperature", float(profile_defaults.get("vieneu_render_temperature") or app_defaults.get("vieneu_render_temperature") or 0.7))
        st.session_state.setdefault("vieneu_render_max_chars_chunk", int(profile_defaults.get("vieneu_render_max_chars_chunk") or app_defaults.get("vieneu_render_max_chars_chunk") or 240))
        st.session_state.setdefault("vieneu_render_use_batch", bool(profile_defaults.get("vieneu_render_use_batch") or app_defaults.get("vieneu_render_use_batch") or False))
        st.session_state.setdefault("vieneu_render_max_batch_size_run", int(profile_defaults.get("vieneu_render_max_batch_size_run") or app_defaults.get("vieneu_render_max_batch_size_run") or 1))
        vieneu_core = normalize_vieneu_core(st.session_state.get("vieneu_core") or "local")
        vieneu_mode_requested = str(st.session_state.get("vieneu_mode") or "turbo")
        vieneu_mode = resolve_vieneu_ui_mode(vieneu_core, vieneu_mode_requested, st.session_state.get("vieneu_device"))
        vieneu_api_base = str(st.session_state.get("vieneu_api_base") or "")
        if vieneu_mode != vieneu_mode_requested:
            st.session_state["vieneu_mode"] = vieneu_mode
            if not is_vieneu_mode_model_compatible(vieneu_mode, st.session_state.get("vieneu_model_name")):
                st.session_state["vieneu_model_name"] = get_default_vieneu_model_name(vieneu_mode)
        vieneu_model_name = resolve_vieneu_model_name(st.session_state.get("vieneu_model_name"), vieneu_mode)
        audio_update_target = str(provider_target_dir("audio", "vieneu", __file__))
        voice_narrator_speed = int(st.session_state.get(VOICE_NARRATOR_SPEED_KEY) or 25)
        voice_female_speed = int(st.session_state.get(VOICE_FEMALE_SPEED_KEY) or 25)
        voice_male_speed = int(st.session_state.get(VOICE_MALE_SPEED_KEY) or 25)
        voice_en_narrator_speed = int(st.session_state.get(VOICE_EN_NARRATOR_SPEED_KEY) or 25)
        voice_en_female_speed = int(st.session_state.get(VOICE_EN_FEMALE_SPEED_KEY) or 25)
        voice_en_male_speed = int(st.session_state.get(VOICE_EN_MALE_SPEED_KEY) or 25)
        vieneu_preview_temperature = float(st.session_state.get("vieneu_preview_temperature") or 0.6)
        vieneu_preview_max_chars_chunk = int(st.session_state.get("vieneu_preview_max_chars_chunk") or 160)
        vieneu_preview_use_batch = bool(st.session_state.get("vieneu_preview_use_batch") or False)
        vieneu_preview_max_batch_size_run = int(st.session_state.get("vieneu_preview_max_batch_size_run") or 1)
        vieneu_preview_text_max_len = int(st.session_state.get("vieneu_preview_text_max_len") or 100)
        vieneu_render_temperature = float(st.session_state.get("vieneu_render_temperature") or 0.7)
        vieneu_render_max_chars_chunk = int(st.session_state.get("vieneu_render_max_chars_chunk") or 240)
        vieneu_render_use_batch = bool(st.session_state.get("vieneu_render_use_batch") or False)
        vieneu_render_max_batch_size_run = int(st.session_state.get("vieneu_render_max_batch_size_run") or 1)
        if tts_provider == "vieneu":
            st.subheader("VieNeu TTS core")
            previous_vieneu_mode = str(st.session_state.get("_vieneu_mode_last") or vieneu_mode or "turbo")
            previous_vieneu_model_name = str(st.session_state.get("vieneu_model_name") or "").strip()
            if str(st.session_state.get("vieneu_core") or "") not in set(VIENEU_CORE_OPTIONS):
                st.session_state["vieneu_core"] = vieneu_core if vieneu_core in set(VIENEU_CORE_OPTIONS) else "local"
            vieneu_core = st.selectbox(
                "VieNeu core",
                list(VIENEU_CORE_OPTIONS),
                key="vieneu_core",
                format_func=lambda value: "headless/local" if value == "local" else "remote API",
                help="Choose how the engine is called: local/headless in this machine or through a remote API.",
            )
            if str(st.session_state.get("vieneu_mode") or "") not in set(VIENEU_MODE_OPTIONS):
                st.session_state["vieneu_mode"] = vieneu_mode if vieneu_mode in set(VIENEU_MODE_OPTIONS) else "turbo"
            vieneu_mode = st.selectbox(
                "VieNeu mode",
                list(VIENEU_MODE_OPTIONS),
                key="vieneu_mode",
                help="turbo = 4 presets; standard = 6 presets. Voice defaults change with the selected mode.",
            )
            previous_default_model = _resolve_vieneu_mode_default_model(
                core=str(st.session_state.get("vieneu_core") or vieneu_core or "local"),
                mode=previous_vieneu_mode,
                current_model=previous_vieneu_model_name,
            )
            current_default_model = _resolve_vieneu_mode_default_model(
                core=str(st.session_state.get("vieneu_core") or vieneu_core or "local"),
                mode=vieneu_mode,
                current_model=previous_vieneu_model_name,
            )
            if not previous_vieneu_model_name or previous_vieneu_model_name == previous_default_model:
                st.session_state["vieneu_model_name"] = current_default_model
            st.session_state["_vieneu_mode_last"] = vieneu_mode
            vieneu_model_name, audio_update_target = _render_audio_local_model_picker(
                provider_id="vieneu",
                current_model=str(st.session_state.get("vieneu_model_name") or "").strip(),
                mode=vieneu_mode,
            )
            if str(st.session_state.get("vieneu_backend") or "") not in set(VIENEU_BACKEND_OPTIONS):
                st.session_state["vieneu_backend"] = "auto"
            vieneu_backend = st.selectbox(
                "Backend",
                list(VIENEU_BACKEND_OPTIONS),
                key="vieneu_backend",
                help="auto chooses the best backend; native forces the built-in path; lmdeploy forces LMDeploy when supported by the selected model.",
            )
            vieneu_runtime_settings = _build_vieneu_runtime_settings(
                core=vieneu_core,
                mode=vieneu_mode,
                api_base=vieneu_api_base,
                model_name=vieneu_model_name,
                local_update_target=audio_update_target,
            )
            runtime_details = get_vieneu_runtime_model_details(vieneu_runtime_settings, allow_network=False)
            st.caption(f"Runtime model: {runtime_details.get('runtime_model') or '-'}")
            st.caption(f"Runtime backend: {runtime_details.get('backend') or '-'} (requested: {runtime_details.get('backend_requested') or 'auto'})")
            if str(runtime_details.get("warning") or "").strip():
                render_user_message(UserMessage(level="warning", title="VieNeu runtime model", body=str(runtime_details.get("warning") or "")))
            if vieneu_core == "local" and vieneu_mode == "standard":
                cached_codec_snapshot = get_vieneu_cached_codec_snapshot()
                st.caption(f"Cached codec snapshot: {cached_codec_snapshot or '-'}")
                st.caption(f"Codec adopt target: {provider_target_dir('audio', 'vieneu_codec', __file__)}")
                if st.button(
                    "Adopt cached codec",
                    width="stretch",
                    key="audio_adopt_cached_codec",
                    disabled=not bool(cached_codec_snapshot),
                    help="Copy the cached codec from Hugging Face into audio/models/vieneu_codec/ for easier local or offline runs.",
                ):
                    try:
                        adopted_path = adopt_vieneu_cached_codec()
                        st.session_state["audio_provider_action_status"] = ("success", f"Adopted cached codec into {adopted_path}")
                        rerun = getattr(st, "rerun", None)
                        if callable(rerun):
                            rerun()
                    except Exception as exc:
                        st.session_state["audio_provider_action_status"] = ("error", format_runtime_error(exc))

                cached_distilhubert_snapshot = get_vieneu_cached_distilhubert_snapshot()
                st.caption(f"Cached distilhubert snapshot: {cached_distilhubert_snapshot or '-'}")
                st.caption(f"Distilhubert adopt target: {provider_target_dir('audio', 'vieneu_distilhubert', __file__)}")
                if st.button(
                    "Adopt cached distilhubert",
                    width="stretch",
                    key="audio_adopt_cached_distilhubert",
                    disabled=not bool(cached_distilhubert_snapshot),
                    help="Copy the cached ntu-spml/distilhubert dependency from Hugging Face into audio/models/vieneu_distilhubert/ to keep a local snapshot in the project.",
                ):
                    try:
                        adopted_path = adopt_vieneu_cached_distilhubert()
                        st.session_state["audio_provider_action_status"] = ("success", f"Adopted cached distilhubert into {adopted_path}")
                        rerun = getattr(st, "rerun", None)
                        if callable(rerun):
                            rerun()
                    except Exception as exc:
                        st.session_state["audio_provider_action_status"] = ("error", format_runtime_error(exc))
            if vieneu_core == "remote_api":
                if not str(st.session_state.get("vieneu_api_base") or "").strip():
                    st.session_state["vieneu_api_base"] = vieneu_api_base or DEFAULT_VIENEU_API_BASE
                st.text_input(
                    "VieNeu API base",
                    help="Example: http://127.0.0.1:23333/v1",
                    key="vieneu_api_base",
                )
                vieneu_api_base = str(st.session_state.get("vieneu_api_base") or "").strip()
            else:
                vieneu_api_base = str(vieneu_api_base or "")
                st.caption("The local/headless core does not use an API base; the engine is called directly in-process.")

            with _expander("VieNeu generation tuning", expanded=False):
                st.caption("These controls are passed to the VieNeu adapter for preview and full render calls.")
                preview_col, render_col = st.columns(2)
                with preview_col:
                    st.markdown("#### Preview")
                    vieneu_preview_temperature = float(
                        st.number_input(
                            "Preview temperature",
                            min_value=0.0,
                            max_value=2.0,
                            value=float(vieneu_preview_temperature),
                            step=0.05,
                            key="vieneu_preview_temperature",
                        )
                    )
                    vieneu_preview_max_chars_chunk = int(
                        st.number_input(
                            "Preview max chars/chunk",
                            min_value=1,
                            max_value=2000,
                            value=int(vieneu_preview_max_chars_chunk),
                            step=10,
                            key="vieneu_preview_max_chars_chunk",
                        )
                    )
                    vieneu_preview_text_max_len = int(
                        st.number_input(
                            "Preview text max length",
                            min_value=1,
                            max_value=2000,
                            value=int(vieneu_preview_text_max_len),
                            step=10,
                            key="vieneu_preview_text_max_len",
                        )
                    )
                    vieneu_preview_use_batch = bool(
                        st.checkbox("Preview batch generation", value=bool(vieneu_preview_use_batch), key="vieneu_preview_use_batch")
                    )
                    vieneu_preview_max_batch_size_run = int(
                        st.number_input(
                            "Preview batch size",
                            min_value=1,
                            max_value=64,
                            value=int(vieneu_preview_max_batch_size_run),
                            step=1,
                            key="vieneu_preview_max_batch_size_run",
                            disabled=not bool(vieneu_preview_use_batch),
                        )
                    )
                with render_col:
                    st.markdown("#### Full render")
                    vieneu_render_temperature = float(
                        st.number_input(
                            "Render temperature",
                            min_value=0.0,
                            max_value=2.0,
                            value=float(vieneu_render_temperature),
                            step=0.05,
                            key="vieneu_render_temperature",
                        )
                    )
                    vieneu_render_max_chars_chunk = int(
                        st.number_input(
                            "Render max chars/chunk",
                            min_value=1,
                            max_value=4000,
                            value=int(vieneu_render_max_chars_chunk),
                            step=10,
                            key="vieneu_render_max_chars_chunk",
                        )
                    )
                    vieneu_render_use_batch = bool(
                        st.checkbox("Render batch generation", value=bool(vieneu_render_use_batch), key="vieneu_render_use_batch")
                    )
                    vieneu_render_max_batch_size_run = int(
                        st.number_input(
                            "Render batch size",
                            min_value=1,
                            max_value=64,
                            value=int(vieneu_render_max_batch_size_run),
                            step=1,
                            key="vieneu_render_max_batch_size_run",
                            disabled=not bool(vieneu_render_use_batch),
                        )
                    )

            col_test, col_refresh, col_update = st.columns([1, 1, 1])
            with col_test:
                if st.button("Test", width="stretch"):
                    try:
                        if tts_provider == "vieneu":
                            message = probe_vieneu_core_connection_from_settings(vieneu_runtime_settings, allow_network=False)
                        else:
                            message = "Audio: edge_tts test OK - local/system provider, no model download is required."
                        st.session_state["audio_provider_action_status"] = ("success", message)
                    except Exception as exc:
                        st.session_state["audio_provider_action_status"] = ("error", format_runtime_error(exc))
            with col_refresh:
                if st.button("Refresh", width="stretch"):
                    try:
                        if tts_provider == "vieneu":
                            message = refresh_vieneu_voices_from_settings(vieneu_runtime_settings, allow_network=False)
                        else:
                            local_models = list_local_models("audio", __file__)
                            message = f"Audio: refreshed edge_tts - models dir={provider_models_dir('audio', __file__)} - local assets={len(local_models)}"
                        st.session_state["audio_provider_action_status"] = ("success", message)
                        rerun = getattr(st, "rerun", None)
                        if callable(rerun):
                            rerun()
                    except Exception as exc:
                        st.session_state["audio_provider_action_status"] = ("error", format_runtime_error(exc))
            with col_update:
                if st.button("Update", width="stretch"):
                    try:
                        if tts_provider == "vieneu":
                            message = refresh_vieneu_voices_from_settings(
                                vieneu_runtime_settings,
                                allow_network=True,
                                force_reload=True,
                            )
                            message = f"{message} | Update target={audio_update_target} | Online mode was enabled temporarily to refresh cache/model assets under models/."
                        else:
                            edge_target = provider_target_dir("audio", "edge_tts", __file__)
                            message = f"Audio: edge_tts has no Update model step. Update target={edge_target}. The app only refreshes local/system voices and does not download anything from the internet."
                        st.session_state["audio_provider_action_status"] = ("success", message)
                        rerun = getattr(st, "rerun", None)
                        if callable(rerun):
                            rerun()
                    except Exception as exc:
                        st.session_state["audio_provider_action_status"] = ("error", format_runtime_error(exc))

            _render_audio_provider_status()
            render_user_message(UserMessage(level="info", title="VieNeu runtime", body="AI-Studio calls VieNeu through the TTS core adapter. The core decides local vs. remote API, and the mode decides which preset/model family is used."))
        st.header(SidebarSection.INPUTS_OUTPUTS)
        output_dir = st.text_input("Output directory", value=str(app_defaults["output_dir"]))
        audio_format = st.selectbox(
            "Audio format",
            ["wav", "mp3"],
            index=0 if app_defaults["audio_format"] == "wav" else 1,
            help="wav = higher-quality master output, mp3 = lighter release file",
        )
        st.header(SidebarSection.RENDER)
        validate_only = st.checkbox("Validate only", value=bool(app_defaults["validate_only"]))
        debug_mode = st.checkbox("Debug only (save segments JSON)", value=bool(app_defaults["debug"]))
        max_concurrent_tts = st.slider(
            "Max concurrent TTS",
            1,
            32,
            int(app_defaults["max_concurrent_tts"]),
            help="Higher values can speed up VieNeu and Edge renders, but may use more CPU/RAM/VRAM.",
        )
        st.caption("Batch Size (Generation) only affects VieNeu Standard/PyTorch; Turbo/GGUF will fall back to single render.")

        with _expander("Render parameters", expanded=True):
            (
                voice_narrator,
                voice_female,
                voice_male,
                voice_en_narrator,
                voice_en_female,
                voice_en_male,
            ) = _render_voice_selector_block(provider=tts_provider, profile_defaults=profile_defaults, advanced=True)

            st.session_state["voice_narrator"] = voice_narrator
            st.session_state["voice_female"] = voice_female
            st.session_state["voice_male"] = voice_male
            st.session_state["voice_en_narrator"] = voice_en_narrator
            st.session_state["voice_en_female"] = voice_en_female
            st.session_state["voice_en_male"] = voice_en_male

            st.subheader("Render behavior")
            sentiment_tone = st.checkbox("Sentiment tone", value=bool(app_defaults["sentiment_tone"]))
            auto_en_lines = st.checkbox("Auto detect English lines", value=bool(app_defaults["auto_en_lines"]))
            post_fx_preset = st.selectbox("Post FX preset", ["none", "storytelling_vi"], index=1 if app_defaults["post_fx_preset"] == "storytelling_vi" else 0)

            st.subheader("History & Batch")
            store_path = st.text_input("Job store path", value=str(DEFAULT_STORE_PATH))

        with _expander(SidebarSection.RUNTIME, expanded=True):
            ffmpeg_exe = st.text_input("ffmpeg executable", value=find_binary(str(app_defaults["ffmpeg_exe"])))
            ffprobe_exe = st.text_input("ffprobe executable", value=find_binary(str(app_defaults["ffprobe_exe"])))
            diagnostics = collect_runtime_diagnostics_for_settings(
                ffmpeg_exe,
                ffprobe_exe,
                tts_provider=tts_provider,
                vieneu_mode=resolve_vieneu_runtime_mode(vieneu_core, vieneu_mode, st.session_state.get("vieneu_device")),
            )
            st.caption("Runtime checks")
            for line in runtime_diagnostics_to_lines(diagnostics):
                st.caption(f"- {line}")

    vieneu_persisted_settings = _build_vieneu_persisted_settings(
        core=vieneu_core,
        mode=vieneu_mode,
        api_base=vieneu_api_base,
        model_name=vieneu_model_name,
        local_update_target=audio_update_target,
    )
    app_config = AppConfig.from_mapping({
        "ffmpeg_exe": ffmpeg_exe,
        "ffprobe_exe": ffprobe_exe,
        "output_dir": output_dir,
        "audio_format": audio_format,
        "tts_provider": tts_provider,
        "validate_only": validate_only,
        "debug_mode": debug_mode,
        "sentiment_tone": sentiment_tone,
        "auto_en_lines": auto_en_lines,
        "post_fx_preset": post_fx_preset,
        "max_concurrent_tts": max_concurrent_tts,
        "store_path": store_path,
        "runtime_diagnostics": diagnostics,
        "vieneu_preview_temperature": vieneu_preview_temperature,
        "vieneu_preview_max_chars_chunk": vieneu_preview_max_chars_chunk,
        "vieneu_preview_use_batch": vieneu_preview_use_batch,
        "vieneu_preview_max_batch_size_run": vieneu_preview_max_batch_size_run,
        "vieneu_preview_text_max_len": vieneu_preview_text_max_len,
        "vieneu_render_temperature": vieneu_render_temperature,
        "vieneu_render_max_chars_chunk": vieneu_render_max_chars_chunk,
        "vieneu_render_use_batch": vieneu_render_use_batch,
        "vieneu_render_max_batch_size_run": vieneu_render_max_batch_size_run,
        **vieneu_persisted_settings,
    })
    profile_config = ProfileConfig.from_mapping({
        "profile_root": profile_root,
        "asset_profile": asset_profile,
        "bgm": bgm,
        "bgmdir": bgmdir,
        "bgm_config": bgm_config,
        "abbr_map": abbr_map,
        "tts_provider": tts_provider,
        "voice_narrator": voice_narrator,
        "voice_female": voice_female,
        "voice_male": voice_male,
        "voice_en_narrator": voice_en_narrator,
        "voice_en_female": voice_en_female,
        "voice_en_male": voice_en_male,
        "voice_narrator_speed": voice_narrator_speed,
        "voice_female_speed": voice_female_speed,
        "voice_male_speed": voice_male_speed,
        "voice_en_narrator_speed": voice_en_narrator_speed,
        "voice_en_female_speed": voice_en_female_speed,
        "voice_en_male_speed": voice_en_male_speed,
        "vieneu_preview_temperature": vieneu_preview_temperature,
        "vieneu_preview_max_chars_chunk": vieneu_preview_max_chars_chunk,
        "vieneu_preview_use_batch": vieneu_preview_use_batch,
        "vieneu_preview_max_batch_size_run": vieneu_preview_max_batch_size_run,
        "vieneu_preview_text_max_len": vieneu_preview_text_max_len,
        "vieneu_render_temperature": vieneu_render_temperature,
        "vieneu_render_max_chars_chunk": vieneu_render_max_chars_chunk,
        "vieneu_render_use_batch": vieneu_render_use_batch,
        "vieneu_render_max_batch_size_run": vieneu_render_max_batch_size_run,
        **vieneu_persisted_settings,
    })
    return GuiConfigBundle(app=app_config, profile=profile_config)



def get_audio_settings() -> GuiConfigBundle:
    return render_settings_sidebar()


def get_settings() -> GuiConfigBundle:
    return get_audio_settings()


def render_settings() -> GuiConfigBundle:
    return get_audio_settings()


def render_sidebar() -> GuiConfigBundle:
    return render_settings_sidebar()

