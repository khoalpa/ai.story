from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from audio.services.vieneu_voice_clone import create_cloned_voice, preview_cloned_voice
from audio.vieneu_voice_store import delete_cloned_voice, list_cloned_voices
from studio.ui_components import confirm_destructive_action


def _is_v3_turbo(settings: dict) -> bool:
    provider = str(settings.get("tts_provider") or "").strip().lower()
    core = str(settings.get("vieneu_core") or "local").strip().lower()
    mode = str(settings.get("vieneu_mode") or "").strip().lower()
    model = str(settings.get("vieneu_model_name") or "").strip().lower()
    return provider == "vieneu" and core == "local" and (mode == "v3turbo" or "v3" in model)


def render_voices_tab(settings: dict) -> None:
    st.subheader("Giọng đã clone")
    st.caption("Tạo và quản lý giọng cá nhân cho VieNeu v3 Turbo. Dữ liệu được lưu cục bộ trên máy này.")

    if not _is_v3_turbo(settings):
        st.info("Chọn VieNeu v3 Turbo trong Settings trước khi tạo hoặc nghe thử giọng clone.")

    voices = list_cloned_voices()
    if voices:
        st.markdown("#### Thư viện giọng")
        for voice in voices:
            with st.container(border=True):
                left, right = st.columns([4, 1])
                with left:
                    st.markdown(f"**🎙 {voice.name}**")
                    details = [voice.language.upper(), voice.model_family]
                    if voice.gender:
                        details.append(voice.gender)
                    st.caption(" · ".join(details))
                    if voice.description:
                        st.write(voice.description)
                with right:
                    confirm = confirm_destructive_action(
                        "Xác nhận xóa",
                        key=f"delete_confirm_{voice.id}",
                        help_text="Giọng clone và dữ liệu cục bộ liên quan sẽ bị xóa.",
                    )
                    if st.button("Xóa", key=f"delete_voice_{voice.id}", disabled=not confirm):
                        delete_cloned_voice(voice.selection_id)
                        st.success(f"Đã xóa giọng {voice.name}.")
                        st.rerun()

        st.markdown("#### Nghe thử")
        selected = st.selectbox(
            "Giọng",
            options=[voice.selection_id for voice in voices],
            format_func=lambda value: next(item.name for item in voices if item.selection_id == value),
            key="cloned_voice_preview_selection",
        )
        preview_text = st.text_area(
            "Văn bản",
            value="Xin chào, đây là bản nghe thử giọng nói đã được tạo bằng VieNeu.",
            max_chars=500,
            key="cloned_voice_preview_text",
        )
        if st.button("Tạo bản nghe thử", disabled=not _is_v3_turbo(settings)):
            try:
                with tempfile.TemporaryDirectory(prefix="ai_studio_voice_preview_") as temp_dir:
                    output = preview_cloned_voice(
                        selected,
                        text=preview_text,
                        output_path=Path(temp_dir) / "preview.wav",
                        model_name=str(settings.get("vieneu_model_name") or ""),
                        device=str(settings.get("vieneu_device") or "cuda"),
                        backend=str(settings.get("vieneu_backend") or "auto"),
                        temperature=float(settings.get("vieneu_preview_temperature") or 0.6),
                    )
                    st.session_state["cloned_voice_preview_audio"] = output.read_bytes()
            except Exception as exc:
                st.error(f"Không thể tạo bản nghe thử: {exc}")
        preview_audio = st.session_state.get("cloned_voice_preview_audio")
        if preview_audio:
            st.audio(preview_audio, format="audio/wav")
    else:
        st.info("Chưa có giọng clone nào.")

    st.markdown("#### Tạo giọng mới")
    uploaded = st.file_uploader(
        "Audio tham chiếu",
        type=["wav", "mp3", "m4a", "flac", "ogg"],
        help="Khuyến nghị 10–30 giây, một người nói, không nhạc nền và ít tiếng ồn.",
        key="cloned_voice_reference_upload",
    )
    if uploaded is not None:
        st.audio(uploaded)
    name = st.text_input("Tên giọng", max_chars=80, key="cloned_voice_name")
    description = st.text_input("Mô tả", max_chars=200, key="cloned_voice_description")
    col1, col2 = st.columns(2)
    with col1:
        language = st.selectbox("Ngôn ngữ", ["vi", "en"], key="cloned_voice_language")
    with col2:
        gender = st.selectbox("Giới tính (tùy chọn)", ["", "Nữ", "Nam", "Khác"], key="cloned_voice_gender")
    keep_audio = st.checkbox(
        "Giữ bản WAV tham chiếu sau khi tạo",
        value=False,
        help="Nếu tắt, hệ thống chỉ giữ embedding và reference codes.",
        key="cloned_voice_keep_audio",
    )
    consent = st.checkbox(
        "Tôi xác nhận mình có quyền và sự đồng ý để sử dụng giọng nói này.",
        key="cloned_voice_consent",
    )
    can_create = uploaded is not None and bool(name.strip()) and consent and _is_v3_turbo(settings)
    if st.button("Tạo giọng clone", type="primary", disabled=not can_create):
        suffix = Path(uploaded.name).suffix or ".audio"
        try:
            with tempfile.TemporaryDirectory(prefix="ai_studio_voice_upload_") as temp_dir:
                source = Path(temp_dir) / f"upload{suffix}"
                source.write_bytes(uploaded.getvalue())
                with st.spinner("Đang phân tích và enroll giọng..."):
                    voice, quality = create_cloned_voice(
                        reference_audio=source,
                        name=name,
                        consent_confirmed=consent,
                        language=language,
                        description=description,
                        gender=gender,
                        keep_reference_audio=keep_audio,
                        model_name=str(settings.get("vieneu_model_name") or ""),
                        device=str(settings.get("vieneu_device") or "cuda"),
                        backend=str(settings.get("vieneu_backend") or "auto"),
                        ffmpeg_exe=str(settings.get("ffmpeg_exe") or "ffmpeg"),
                    )
            st.success(f"Đã tạo giọng {voice.name} từ mẫu dài {quality.duration_seconds:.1f} giây.")
            if quality.warning:
                st.warning(quality.warning)
            st.rerun()
        except Exception as exc:
            st.error(f"Không thể tạo giọng clone: {exc}")
