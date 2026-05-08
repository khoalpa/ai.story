from __future__ import annotations

from pathlib import Path

import streamlit as st

from audio.gui.service import _resolve_vieneu_device_for_runtime, describe_vieneu_cuda_turbo_path, resolve_vieneu_runtime_mode
from audio.render_job_repository import JobRepository
from audio.runtime_checks import collect_runtime_diagnostics_for_settings, runtime_diagnostics_to_lines
from audio.gui.diagnostics_blocks import render_runtime_diagnostics_block

from .batch import render_batch_tab as _render_batch_tab
from .constants import DEFAULT_STORE_PATH
from .history import render_run_history
from .run_panel import render_input_tab as _render_input_tab
from .run_panel import render_preview_tab, render_run_tab as _render_run_tab, render_test_tts_tab as _render_test_tts_tab


def _build_repository(settings: dict) -> JobRepository:
    store_path = Path(str(settings.get("store_path") or DEFAULT_STORE_PATH))
    store_path.parent.mkdir(parents=True, exist_ok=True)
    return JobRepository(str(store_path))


def render_input_tab(settings: dict) -> None:
    del settings
    _render_input_tab()


def render_run_tab(settings: dict) -> None:
    repository = _build_repository(settings)
    _render_run_tab(settings, repository)


def render_test_tts_tab(settings: dict) -> None:
    _render_test_tts_tab(settings)


def render_preview_logs_tab(settings: dict) -> None:
    repository = _build_repository(settings)
    render_preview_tab()
    st.divider()
    render_run_history(repository)


def render_batch_tab(settings: dict) -> None:
    repository = _build_repository(settings)
    _render_batch_tab(settings, repository)


def _doctor_asset_rows(settings: dict) -> list[dict[str, str]]:
    profile_root = Path(str(settings.get("profile_root") or "")).expanduser()
    asset_profile = str(settings.get("asset_profile") or "").strip()
    profile_dir = profile_root / asset_profile if profile_root and asset_profile else None
    demo_manifest = profile_dir / "manifest.json" if profile_dir is not None else None
    bgm_dir = Path(str(settings.get("bgmdir") or "")).expanduser() if str(settings.get("bgmdir") or "").strip() else None
    abbr_map = Path(str(settings.get("abbr_map") or "")).expanduser() if str(settings.get("abbr_map") or "").strip() else None
    bgm_config = Path(str(settings.get("bgm_config") or "")).expanduser() if str(settings.get("bgm_config") or "").strip() else None

    rows = [
        {"check": "Profile root", "path": str(profile_root), "status": "OK" if profile_root.is_dir() else "missing"},
        {"check": "Asset profile", "path": str(profile_dir or ""), "status": "OK" if profile_dir is not None and profile_dir.is_dir() else ("not set" if not asset_profile else "missing")},
        {"check": "Profile manifest", "path": str(demo_manifest or ""), "status": "OK" if demo_manifest is not None and demo_manifest.is_file() else ("not set" if demo_manifest is None else "missing")},
        {"check": "BGM dir", "path": str(bgm_dir or ""), "status": "OK" if bgm_dir is not None and bgm_dir.is_dir() else ("not set" if bgm_dir is None else "missing")},
        {"check": "Abbreviation map", "path": str(abbr_map or ""), "status": "OK" if abbr_map is not None and abbr_map.is_file() else ("not set" if abbr_map is None else "missing")},
        {"check": "BGM config", "path": str(bgm_config or ""), "status": "OK" if bgm_config is not None and bgm_config.is_file() else ("not set" if bgm_config is None else "missing")},
    ]
    return rows


def render_doctor_tab(settings: dict) -> None:
    st.subheader("Audio doctor")
    diagnostics = collect_runtime_diagnostics_for_settings(
        str(settings.get("ffmpeg_exe") or ""),
        str(settings.get("ffprobe_exe") or ""),
        tts_provider=str(settings.get("tts_provider") or "edge"),
        vieneu_mode=str(settings.get("vieneu_mode") or "standard"),
    )

    runtime_lines = runtime_diagnostics_to_lines(diagnostics)
    ok_count = sum(1 for line in runtime_lines if "available" in line.lower() or "ok" in line.lower())
    issue_count = len(runtime_lines) - ok_count
    col1, col2, col3 = st.columns(3)
    col1.metric("TTS provider", str(settings.get("tts_provider") or "-"))
    col2.metric("Runtime checks", len(runtime_lines))
    col3.metric("Issues", max(issue_count, 0))

    render_device = str(settings.get("vieneu_device") or "auto").strip().lower() or "auto"
    effective_mode = resolve_vieneu_runtime_mode(settings.get("vieneu_core"), settings.get("vieneu_mode"), render_device)
    runtime_device = _resolve_vieneu_device_for_runtime(render_device)
    is_vieneu = str(settings.get("tts_provider") or "edge").strip().lower() == "vieneu"
    promoted_standard = is_vieneu and render_device == "auto" and runtime_device == "cuda" and effective_mode == "standard"

    if render_device == "auto":
        badge_label = "Render audio: auto -> standard" if promoted_standard else "Render audio: auto -> cpu"
    else:
        badge_label = f"Render audio: {render_device}"
    badge_color = "#bfdbfe" if promoted_standard else ("#dbeafe" if runtime_device == "cuda" else "#e2e8f0")
    badge_text = "#1d4ed8" if runtime_device == "cuda" else "#334155"

    st.markdown(
        f"<span style='display:inline-block;padding:0.18rem 0.55rem;border-radius:999px;"
        f"background:{badge_color};color:{badge_text};font-size:0.78rem;font-weight:700;"
        f"line-height:1.1'>{badge_label}</span>",
        unsafe_allow_html=True,
    )

    effective_mode_label = "standard" if promoted_standard else str(effective_mode or settings.get("vieneu_mode") or "standard")
    if promoted_standard:
        effective_mode_label = "<span style='color:#1d4ed8;font-weight:700;'>standard</span>"
    st.caption(
        "VieNeu effective mode: "
        f"{effective_mode_label} | device={render_device} (internal={runtime_device}) | "
        f"model={str(settings.get('vieneu_model_name') or '-').strip() or '-'}"
    )

    if is_vieneu and runtime_device == "cuda":
        cuda_notice = describe_vieneu_cuda_turbo_path(
            core=settings.get("vieneu_core"),
            mode=settings.get("vieneu_mode"),
            device=render_device,
        )
        if cuda_notice:
            st.warning(cuda_notice)

    for line in runtime_lines:
        normalized = line.lower()
        if any(token in normalized for token in ["missing", "not installed", "not found", "error"]):
            st.error(line)
        else:
            st.success(line)

    st.markdown("#### Asset & config health")
    st.dataframe(_doctor_asset_rows(settings), width="stretch", height=245)

    summary = {
        "profile_root": str(settings.get("profile_root") or ""),
        "asset_profile": str(settings.get("asset_profile") or ""),
        "tts_provider": str(settings.get("tts_provider") or ""),
        "vieneu_core": str(settings.get("vieneu_core") or ""),
        "vieneu_mode": str(settings.get("vieneu_mode") or ""),
        "vieneu_api_base": str(settings.get("vieneu_api_base") or ""),
        "vieneu_model_name": str(settings.get("vieneu_model_name") or ""),
        "vieneu_device": str(settings.get("vieneu_device") or ""),
        "ffmpeg_exe": str(settings.get("ffmpeg_exe") or ""),
        "ffprobe_exe": str(settings.get("ffprobe_exe") or ""),
        "output_dir": str(settings.get("output_dir") or ""),
        "audio_format": str(settings.get("audio_format") or ""),
    }
    render_runtime_diagnostics_block(summary, label="Current Audio settings", expanded=False)
    render_runtime_diagnostics_block(diagnostics, label="Raw runtime diagnostics", expanded=False, serializer=lambda info: info.as_dict())
