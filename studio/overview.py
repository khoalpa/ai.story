"""Project-level dashboard for the unified Studio workspace."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from studio.package_quality_report import _items, _object
from studio.story_studio import REPORT_SPECS, load_story_package
from studio.story_validation_report import _all_gates_pass

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _existing_path(value: Any, *, root: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve() if path.exists() else None


def _display_score(value: Any, maximum: int) -> str:
    if value in {None, "", "—"}:
        return "—"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "—"
    if maximum == 10 and score > 10:
        score /= 10
    return f"{score:.1f}/{maximum}"


def build_overview_model(
    reports: Mapping[str, Mapping[str, Any]],
    statuses: Mapping[str, str],
    state: Mapping[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Build a presentation-neutral overview from reports and current session state."""
    story = _object(reports.get("story"))
    validation = _object(reports.get("validation"))
    quality = _object(reports.get("quality"))
    anchor = _object(reports.get("anchor"))
    meta = _object(story.get("meta"))
    commitment = _object(meta.get("story_quality_commitment"))
    metrics = _object(commitment.get("recomputable_metrics")) or _object(validation.get("summary"))
    committed_quality = _object(commitment.get("committed_quality_metrics"))
    validation_quality = _object(validation.get("quality"))
    quality_summary = _object(quality.get("summary"))
    continuity = _object(anchor.get("continuity"))
    blockers = _items(quality.get("blockers"))
    defects = int(_object(validation.get("summary")).get("material_defect_remaining_count") or 0)

    audio_summary = _object(state.get("last_result_summary"))
    video_summary = _object(state.get("video_last_summary"))
    root = Path.cwd()
    audio_path = _existing_path(
        audio_summary.get("out_file") or state.get("audio_last_output"), root=root
    )
    subtitle_path = _existing_path(
        audio_summary.get("srt_path") or state.get("audio_last_srt_output"), root=root
    )
    video_path = _existing_path(
        state.get("video_last_output") or video_summary.get("output"), root=root
    )
    scenes_dir = _existing_path(
        video_summary.get("scenes_dir") or state.get("video_scenes_input"), root=root
    )
    scene_count = 0
    if scenes_dir and scenes_dir.is_dir():
        scene_count = sum(path.suffix.lower() in IMAGE_SUFFIXES for path in scenes_dir.iterdir() if path.is_file())
    expected_scenes = int(metrics.get("narrative_scene_count") or 0)

    production_ready = bool(validation) and _all_gates_pass(validation) and defects == 0
    publish_ready = bool(quality) and quality_summary.get("publish_verdict") == "PASS"
    if blockers or (validation and not production_ready):
        verdict = "Cần xử lý"
        verdict_kind = "error"
    elif publish_ready and production_ready and video_path:
        verdict = "Sẵn sàng xuất bản"
        verdict_kind = "success"
    elif production_ready:
        verdict = "Sẵn sàng sản xuất"
        verdict_kind = "info"
    else:
        verdict = "Chưa đủ dữ liệu"
        verdict_kind = "warning"

    title = str(meta.get("title") or _object(quality.get("package_identity")).get("title") or "Dự án chưa đặt tên")
    episode = meta.get("episode") or continuity.get("latest_episode")
    series = str(meta.get("series") or _object(anchor.get("series")).get("title") or "")
    project_label = title + (f" · Tập {episode}" if episode not in {None, ""} else "")
    missing = [REPORT_SPECS[key][1] for key, status in statuses.items() if status == "Thiếu"]

    actions: list[dict[str, str]] = []
    if missing:
        actions.append({"workspace": "Story Studio", "text": "Bổ sung dữ liệu: " + ", ".join(missing) + "."})
    if defects:
        actions.append({"workspace": "Story Studio", "text": f"Xử lý {defects} lỗi nội dung còn lại."})
    if blockers:
        actions.append({"workspace": "Story Studio", "text": f"Xử lý {len(blockers)} lỗi chặn xuất bản."})
    if not audio_path:
        actions.append({"workspace": "Audio Studio", "text": "Render audio và phụ đề từ kịch bản."})
    elif not video_path:
        asset_note = ""
        if expected_scenes and scene_count < expected_scenes:
            asset_note = f"; hiện có {scene_count}/{expected_scenes} ảnh cảnh"
        actions.append({"workspace": "Video Studio", "text": "Chuẩn bị asset và render video" + asset_note + "."})
    if not actions:
        actions.append({"workspace": "Overview", "text": "Không có hành động bắt buộc; dự án đã sẵn sàng."})

    candidates = [
        path for path in (output_dir / name for name, _label, _validator in REPORT_SPECS.values()) if path.exists()
    ] + [path for path in (audio_path, subtitle_path, video_path) if path]
    last_updated = max((path.stat().st_mtime for path in candidates), default=None)

    return {
        "project_label": project_label,
        "series": series,
        "output_dir": str(output_dir.resolve()),
        "verdict": verdict,
        "verdict_kind": verdict_kind,
        "updated": datetime.fromtimestamp(last_updated).strftime("%d/%m/%Y %H:%M") if last_updated else "—",
        "metrics": [
            ("Thời lượng dự kiến", f"{float(metrics.get('estimated_duration_minutes') or 0):.1f} phút" if metrics else "—"),
            ("Số từ", f"{int(metrics.get('total_words') or 0):,}" if metrics else "—"),
            ("Số cảnh", str(expected_scenes) if expected_scenes else "—"),
            ("Chất lượng truyện", _display_score(committed_quality.get("final_story_quality_score", validation_quality.get("final_story_quality_score")), 10)),
            ("Chất lượng gói", _display_score(quality_summary.get("overall_score"), 100)),
            ("Lỗi cần xử lý", str(defects + len(blockers))),
        ],
        "pipeline": [
            ("Story", "Đạt" if production_ready else ("Cần xử lý" if validation else "Chưa có")),
            ("Audio", "Đã render" if audio_path else "Chưa render"),
            ("Video", "Đã render" if video_path else ("Chờ asset" if audio_path else "Chưa sẵn sàng")),
            ("Publish", "Sẵn sàng" if publish_ready and video_path else "Chưa sẵn sàng"),
        ],
        "audio": {
            "TTS provider": audio_summary.get("tts_provider", "—"),
            "Định dạng": str(audio_summary.get("audio_format") or "—").upper(),
            "Pacing": audio_summary.get("pacing_preset", "—"),
            "Loudness": audio_summary.get("loudness_profile", "—"),
            "Nhạc nền": audio_summary.get("bgm", "—"),
            "Segments": audio_summary.get("segment_count", "—"),
        },
        "video": {
            "Chế độ": video_summary.get("mode", "—"),
            "Tỷ lệ": video_summary.get("aspect", "—"),
            "Encoding": video_summary.get("encoding_profile", "—"),
            "FPS": video_summary.get("video_fps", "—"),
            "Phụ đề": "Bật" if video_summary.get("show_subtitles") else ("Tắt" if video_summary else "—"),
            "Ảnh cảnh": f"{scene_count}/{expected_scenes}" if expected_scenes else (str(scene_count) if scene_count else "—"),
        },
        "resources": [
            ("Kịch bản", "Có dữ liệu" if story else "Thiếu", f"{int(metrics.get('total_words') or 0):,} từ" if metrics else "—", str(output_dir / "story.json") if story else ""),
            ("Audio", "Hoàn tất" if audio_path else "Chưa render", str(audio_summary.get("estimated_duration") or audio_summary.get("audio_format") or "—"), str(audio_path or "")),
            ("Phụ đề", "Hoàn tất" if subtitle_path else "Chưa có", str(audio_summary.get("segment_count") or "—"), str(subtitle_path or "")),
            ("Ảnh cảnh", "Đủ" if expected_scenes and scene_count >= expected_scenes else ("Thiếu" if expected_scenes else "Chưa xác định"), f"{scene_count}/{expected_scenes}" if expected_scenes else str(scene_count), str(scenes_dir or "")),
            ("Video", "Hoàn tất" if video_path else "Chưa render", str(video_summary.get("aspect") or "—"), str(video_path or "")),
        ],
        "actions": actions,
    }


def render_overview() -> None:
    import streamlit as st

    default_dir = str((Path.cwd() / "output").resolve())
    output_text = st.text_input(
        "Thư mục dữ liệu dự án",
        value=st.session_state.get("studio_overview_output_dir", default_dir),
        key="studio_overview_output_dir",
        help="Đọc tự động story.json, báo cáo chất lượng và các đầu ra sản xuất.",
    )
    output_dir = Path(output_text.strip()).expanduser()
    reports, statuses = load_story_package(output_dir)
    model = build_overview_model(reports, statuses, st.session_state, output_dir=output_dir)

    st.caption("TỔNG QUAN DỰ ÁN")
    st.subheader(model["project_label"])
    updated_label = f"Cập nhật {model['updated']}" if model["updated"] != "—" else ""
    subtitle = " · ".join(part for part in (model["series"], updated_label) if part)
    if subtitle:
        st.caption(subtitle)
    getattr(st, model["verdict_kind"])(f"**{model['verdict']}** · Dữ liệu tại `{model['output_dir']}`")

    columns = st.columns(6)
    for column, (label, value) in zip(columns, model["metrics"]):
        column.metric(label, value)

    st.subheader("Tiến độ pipeline")
    pipeline_columns = st.columns(4)
    for index, (column, (label, status)) in enumerate(zip(pipeline_columns, model["pipeline"]), start=1):
        icon = "✓" if status in {"Đạt", "Đã render", "Sẵn sàng"} else ("!" if status in {"Cần xử lý", "Chờ asset"} else "○")
        column.markdown(f"**{index}. {label}**  \n{icon} {status}")

    st.subheader("Thông số sản xuất")
    audio_col, video_col = st.columns(2)
    for column, heading, values in ((audio_col, "Audio", model["audio"]), (video_col, "Video", model["video"])):
        with column:
            st.markdown(f"**{heading}**")
            st.table([{"Thông số": key, "Giá trị": value} for key, value in values.items()])

    st.subheader("Tài nguyên và đầu ra")
    st.dataframe(
        [{"Thành phần": name, "Trạng thái": status, "Thông tin": info, "Đường dẫn": path} for name, status, info, path in model["resources"]],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Hành động ưu tiên")
    for index, action in enumerate(model["actions"]):
        text_col, button_col = st.columns([5, 1])
        text_col.markdown(f"- {action['text']}")
        if action["workspace"] != "Overview" and button_col.button(f"Mở {action['workspace']}", key=f"overview_action_{index}"):
            st.session_state["studio_workspace"] = action["workspace"]
            st.rerun()


__all__ = ["build_overview_model", "render_overview"]
