from __future__ import annotations

from audio.providers.base import TtsProviderDescriptor, VoiceChoice

PROVIDER_ID = "vieneu"
CORE_OPTIONS = ("local", "remote_api")
MODE_OPTIONS = ("turbo", "standard")
BACKEND_OPTIONS = ("auto", "native", "lmdeploy")
RENDER_AUDIO_OPTIONS = ("auto", "cpu")
DEFAULT_CORE = "local"
DEFAULT_MODE = "standard"
DEFAULT_BACKEND = "auto"
DEFAULT_RENDER_AUDIO = "auto"

try:
    from audio.adapters.tts_core import (
        _static_vieneu_sample_voices,
        migrate_vieneu_legacy_voice_id,
        resolve_vieneu_model_name,
    )
except Exception:  # pragma: no cover

    def migrate_vieneu_legacy_voice_id(voice_id: object, available_choices: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> str:
        return str(voice_id or "").strip()

    def _static_vieneu_sample_voices(mode: object = "standard", model_name: object = "") -> tuple[tuple[str, str], ...]:
        if str(mode or "standard").strip().lower() == "standard":
            return (
                ("Vinh (Nam - Mien Nam)", "Vinh"),
                ("Binh (Nam - Mien Bac)", "Binh"),
                ("Tuyen (Nam - Mien Bac)", "Tuyen"),
                ("Doan (Nu - Mien Nam)", "Doan"),
                ("Ly (Nu - Mien Bac)", "Ly"),
                ("Ngoc (Nu - Mien Bac)", "Ngoc"),
            )
        return (
            ("Bich Ngoc (Nu - Mien Bac)", "Bich Ngoc"),
            ("Pham Tuyen (Nam - Mien Bac)", "Pham Tuyen"),
            ("Thuc Doan (Nu - Mien Nam)", "Thuc Doan"),
            ("Xuan Vinh (Nam - Mien Nam)", "Xuan Vinh"),
        )

    def resolve_vieneu_model_name(model_name: object = "", mode: object = "standard") -> str:
        return str(model_name or "").strip()


def _infer_lang(desc: object, voice_id: object) -> str:
    lower = f"{desc or ''} {voice_id or ''}".strip().lower()
    if any(token in lower for token in ("english", " en ", "en-", "en_", "eng ", "eng-", "eng_")):
        return "en"
    return "vi"


def _infer_gender(desc: object, voice_id: object) -> str | None:
    lower = f"{desc or ''} {voice_id or ''}".strip().lower()
    if any(token in lower for token in ("nu", "nữ", "female", "girl", "woman", "fem")):
        return "female"
    if any(token in lower for token in ("nam", "male", "boy", "man", "masc")):
        return "male"
    return None


def _runtime_voice_choices() -> tuple[tuple[str, str], ...]:
    try:
        import streamlit as st  # type: ignore

        vieneu_core = str(st.session_state.get("vieneu_core") or DEFAULT_CORE)
        vieneu_mode = str(st.session_state.get("vieneu_mode") or DEFAULT_MODE)
        vieneu_api_base = str(st.session_state.get("vieneu_api_base") or "")
        vieneu_model_name = resolve_vieneu_model_name(st.session_state.get("vieneu_model_name"), vieneu_mode)
        cache_key = "|".join((vieneu_core, vieneu_mode, vieneu_api_base, vieneu_model_name or ""))
        if str(st.session_state.get("vieneu_voice_catalog_tested_key") or "") == cache_key:
            return tuple(st.session_state.get("vieneu_voice_catalog_choices") or ())
    except Exception:
        pass
    return tuple()


def get_voice_choices(*, lang: str, role: str) -> tuple[VoiceChoice, ...]:
    try:
        import streamlit as st  # type: ignore
        vieneu_mode = str(st.session_state.get("vieneu_mode") or DEFAULT_MODE)
        vieneu_model_name = resolve_vieneu_model_name(st.session_state.get("vieneu_model_name"), vieneu_mode)
    except Exception:
        vieneu_mode = DEFAULT_MODE
        vieneu_model_name = resolve_vieneu_model_name("", vieneu_mode)

    available = _runtime_voice_choices()
    if not available:
        fallback_mode = "standard" if vieneu_mode == "standard" else "turbo"
        available = tuple(_static_vieneu_sample_voices(mode=fallback_mode, model_name=vieneu_model_name))

    target_lang = str(lang or "vi").strip().lower() or "vi"
    target_role = str(role or "narrator").strip().lower() or "narrator"
    choices: list[VoiceChoice] = []
    for desc, voice_id in available:
        clean_voice_id = migrate_vieneu_legacy_voice_id(voice_id, available)
        inferred_lang = _infer_lang(desc, clean_voice_id)
        if inferred_lang != target_lang:
            continue
        inferred_gender = _infer_gender(desc, clean_voice_id)
        effective_role = inferred_gender if inferred_gender in {"female", "male"} else "narrator"
        if target_role not in {"narrator", effective_role}:
            continue
        label = str(desc or clean_voice_id).strip() or clean_voice_id
        choices.append(VoiceChoice(clean_voice_id, f"{label} (VieNeu)", target_lang, effective_role))

    if choices:
        return tuple(choices)
    return tuple(VoiceChoice(str(voice_id), f"{str(desc)} (VieNeu)", target_lang, "narrator") for desc, voice_id in available)


DESCRIPTOR = TtsProviderDescriptor(
    provider_id=PROVIDER_ID,
    label="VieNeu TTS core",
    description="TTS tieng Viet dung qua VieNeu TTS core (headless/local hoac remote API).",
    requires_network=False,
    optional_dependency="vieneu",
    aliases=("vieneu", "vieneutts", "vieneucore", "vieneu-core", "vie-neu", "local", "offline", "system"),
    sort_order=10,
    voice_choices=lambda lang, role: get_voice_choices(lang=lang, role=role),
)
