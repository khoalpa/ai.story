from __future__ import annotations

from pathlib import Path

import streamlit as st

from .helpers import build_output_zip, output_download_name
from .user_messages import show_preview_warning


def render_preview_table() -> None:
    segments = st.session_state.get("last_preview_segments", [])
    if not segments:
        show_preview_warning(
            "segment preview",
            reason="Run validate or render first to build the segment list.",
            actions=["Open the Run tab and use Quick Validate or Run pipeline.", "Return after new results are available."],
        )
        return
    rows = [
        {
            "#": idx,
            "voice": getattr(seg, "voice", ""),
            "lang": getattr(seg, "lang", ""),
            "zone": getattr(seg, "zone", ""),
            "env": getattr(seg, "env", ""),
            "bgm": getattr(seg, "bgm", ""),
            "ambience": getattr(seg, "ambience", ""),
            "rate": getattr(seg, "rate", ""),
            "pause_before_ms": getattr(seg, "pause_ms_before", 0),
            "text": getattr(seg, "text", ""),
        }
        for idx, seg in enumerate(segments, start=1)
    ]
    st.dataframe(rows, width="stretch", height=420)


def _audio_download_meta(out_file: str | None, summary: dict) -> tuple[str, str]:
    path = Path(out_file) if out_file else None
    ext = path.suffix.lower() if path else ""
    fmt = str(summary.get("audio_format", "")).strip().lower()
    return ("Download WAV", "audio/wav") if ext == ".wav" or fmt == "wav" else ("Download MP3", "audio/mpeg")


def render_output_downloads(summary: dict) -> None:
    artifacts = (
        (summary.get("out_file"), "audio"),
        (summary.get("srt_path"), "text/plain"),
        (summary.get("quality_report"), "application/json"),
        (summary.get("debug_json"), "application/json"),
    )
    cols = st.columns(4)
    for col, (raw_path, mime) in zip(cols, artifacts):
        if not raw_path or not Path(raw_path).is_file():
            continue
        path = Path(raw_path)
        with col:
            if mime == "audio":
                label, resolved_mime = _audio_download_meta(str(path), summary)
                st.audio(str(path))
            else:
                labels = {".srt": "Download SRT", ".json": "Download JSON"}
                label, resolved_mime = labels.get(path.suffix.lower(), "Download file"), mime
                if raw_path == summary.get("quality_report"):
                    label = "Download Quality Report"
                elif raw_path == summary.get("debug_json"):
                    label = "Download Debug JSON"
            st.download_button(label, data=path.read_bytes(), file_name=path.name, mime=resolved_mime, width="stretch")

    bundle = build_output_zip(summary)
    if bundle is not None:
        st.download_button(
            "Download output bundle (.zip)",
            data=bundle,
            file_name=output_download_name(),
            mime="application/zip",
            width="stretch",
        )


def render_final_segment_rate_debug() -> None:
    segments = st.session_state.get("last_preview_segments", [])
    if not segments:
        return
    rows = []
    for idx, seg in enumerate(segments, start=1):
        text = str(getattr(seg, "text", "") or "").strip()
        rows.append({
            "#": idx,
            "voice": getattr(seg, "voice", ""),
            "lang": getattr(seg, "lang", ""),
            "rate": getattr(seg, "rate", ""),
            "pause_before_ms": getattr(seg, "pause_ms_before", 0),
            "text": text[:96] + ("..." if len(text) > 96 else ""),
        })
    with st.expander("Final segment rates", expanded=False):
        st.caption("Final per-segment rate after defaults, tags, and sentiment adjustments.")
        st.dataframe(rows, width="stretch", height=260)
