"""Project-level dashboard for the unified Studio workspace."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from studio.audio_delivery_report import format_duration, inspect_audio_delivery
from studio.package_quality_report import _items, _object
from studio.project_context import (
    OVERVIEW_DIRECTORY_KEY,
    apply_project_directory,
    choose_project_directory,
)
from studio.project_review import required_report_keys, review_package
from studio.report_semantics import (
    display_coverage,
    display_score,
    gate_summary,
)
from studio.story_images import (
    EXPECTED_IMAGE_STEMS,
    inspect_story_images,
    render_aspect_cover_gallery,
)
from studio.story_repetition import analyze_story_repetition
from studio.story_studio import (
    REPORT_SPECS,
    load_effective_package,
    render_source_provenance,
)
from studio.video_delivery_report import build_video_delivery_summary
from studio.workflow_views import render_workflow_summary

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _video_aspect_name(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("×", "x")
    return "portrait" if normalized in {"portrait", "9x16", "9:16"} else "landscape"


def _existing_path(value: Any, *, root: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve() if path.exists() else None


_display_score = display_score

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
    repetition = analyze_story_repetition(story) if story else {"summary": {}}
    repetition_summary = _object(repetition.get("summary"))
    repetition_pairs = int(repetition_summary.get("pair_count") or 0)
    repeated_sentences = int(repetition_summary.get("affected_sentence_count") or 0)
    image_assets = inspect_story_images(output_dir)

    # The settings snapshots make this section useful before a render and keep
    # it populated when Streamlit stops rendering the workspace-owned widgets.
    # A completed run remains authoritative for fields captured at render time.
    audio_summary = {
        **_object(state.get("audio_production_settings")),
        **_object(state.get("last_result_summary")),
    }
    video_summary = {
        **_object(state.get("video_production_settings")),
        **_object(state.get("video_last_summary")),
    }
    root = Path.cwd()
    audio_path = _existing_path(
        audio_summary.get("out_file") or state.get("audio_last_output"), root=root
    )
    subtitle_path = _existing_path(
        audio_summary.get("srt_path") or state.get("audio_last_srt_output"), root=root
    )
    delivery = inspect_audio_delivery(reports, output_dir)
    handoff_audio = next(
        (row["path"] for row in delivery["artifacts"] if row["key"] == "audio" and row["exists"]),
        None,
    )
    handoff_subtitle = next(
        (row["path"] for row in delivery["artifacts"] if row["key"] == "subtitle" and row["exists"]),
        None,
    )
    audio_path = audio_path or handoff_audio
    subtitle_path = subtitle_path or handoff_subtitle
    video_path = _existing_path(
        state.get("video_last_output") or video_summary.get("output"), root=root
    )
    video_variants = reports.get("video_deliveries")
    video_deliveries = build_video_delivery_summary(
        video_variants if isinstance(video_variants, Mapping) else {}, output_dir
    )
    manifest_video = next((item["video_path"] for item in video_deliveries if item["video_path"]), None)
    video_path = video_path or manifest_video
    for item in video_deliveries:
        item["ready"] = item["ready"] and not item["failed_checks"]
    ready_videos = sum(item["ready"] for item in video_deliveries)
    selected_aspect = _video_aspect_name(video_summary.get("aspect") or state.get("video_aspect"))
    selected_images = image_assets[selected_aspect]
    scenes_dir = _existing_path(
        video_summary.get("scenes_dir")
        or state.get("video_input_scenes_dir")
        or state.get("video_scenes_input"),
        root=root,
    ) or Path(selected_images["directory"])
    # The canonical image manifest is authoritative for project artwork. This
    # avoids counting cover/outro differently from Story Studio and prevents a
    # narrative-scene metric from being compared with a fixed production set.
    if scenes_dir.resolve() == Path(selected_images["directory"]).resolve():
        scene_count = int(selected_images["count"])
        required_scene_images = int(selected_images["expected"])
    else:
        available_stems = {
            path.stem.casefold()
            for path in scenes_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        } if scenes_dir.is_dir() else set()
        scene_count = sum(stem in available_stems for stem in EXPECTED_IMAGE_STEMS)
        required_scene_images = len(EXPECTED_IMAGE_STEMS)
    expected_scenes = int(metrics.get("narrative_scene_count") or 0)

    review = review_package(output_dir, reports, statuses, state)
    workflow = review["workflow"]
    stage = workflow["stage"]
    production_ready = review["story_ready"]
    completed = bool(delivery["ready"] and delivery["passed"] and video_deliveries and ready_videos == len(video_deliveries))
    if stage or workflow["status"] == "FAIL":
        verdict = "Gói có lỗi cần xử lý" if workflow["status"] == "FAIL" else "Gói chưa được xác minh đầy đủ"
        verdict_kind = "error" if workflow["status"] == "FAIL" else "warning"
    elif blockers or review["issues"] or (validation and not production_ready):
        verdict = "Cần xử lý"
        verdict_kind = "error"
    elif completed:
        verdict = "Media đạt kiểm định · gói truyện chưa xác minh"
        verdict_kind = "info"
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
    missing = [
        label
        for key, (_filename, label, _validator) in REPORT_SPECS.items()
        if statuses.get(key) == "Thiếu" and key in required_report_keys(reports)
    ]

    actions: list[dict[str, str]] = [
        {"workspace": "Story Studio", "section": issue["section"], "text": issue["text"]}
        for issue in review["issues"]
    ]
    if story and not stage:
        actions.insert(0, {"workspace": "Story Studio", "section": "Gói & quy trình", "text": "Mở story.zip để kiểm tra manifest; không suy stage từ thư mục hoặc tên file."})
    asset_problems = review["asset_issues"] if story else []
    if asset_problems:
        examples = "; ".join(f"{row['name']}: {row['status']}" for row in asset_problems[:3])
        actions.append({"workspace": "Story Studio", "section": "Tài nguyên", "text": f"{len(asset_problems)} ảnh cần kiểm tra · {examples}"})
    if missing:
        actions.append({"workspace": "Story Studio", "text": "Bổ sung dữ liệu: " + ", ".join(missing) + "."})
    if defects:
        actions.append({"workspace": "Story Studio", "section": "Kiểm định", "text": f"Xử lý {defects} lỗi nội dung còn lại."})
    if blockers:
        actions.append({"workspace": "Story Studio", "section": "Chất lượng", "text": f"Xử lý {len(blockers)} lỗi chặn xuất bản."})
    if repetition_pairs:
        actions.append({
            "workspace": "Story Studio",
            "text": f"Xem lại {repetition_pairs} cặp câu lặp hoặc gần trùng trong Nội dung → Lặp câu.",
        })
    if stage in {"STAGE1", "STAGE2"}:
        actions.append({"workspace": "Story Studio", "section": "Gói & quy trình", "text": "Hoàn tất kiểm định gói hiện tại trước khi chuyển stage thủ công; chưa yêu cầu render audio/video."})
    elif not audio_path:
        actions.append({"workspace": "Audio Studio", "text": "Render audio và phụ đề từ kịch bản."})
    elif reports.get("audio_quality") and not delivery["passed"]:
        actions.append({"workspace": "Story Studio", "text": "Mở Âm thanh & phụ đề và xử lý các phép kiểm tra audio chưa đạt."})
    elif delivery["issues"]:
        actions.append({"workspace": "Story Studio", "text": delivery["issues"][0]})
    elif video_deliveries and ready_videos < len(video_deliveries):
        failed_labels = ", ".join(item["label"] for item in video_deliveries if not item["ready"])
        actions.append({"workspace": "Story Studio", "text": f"Mở Video đầu ra và kiểm tra: {failed_labels}."})
    elif not video_path:
        asset_note = ""
        if required_scene_images and scene_count < required_scene_images:
            asset_note = f"; hiện có {scene_count}/{required_scene_images} ảnh {selected_aspect}"
        actions.append({"workspace": "Video Studio", "text": "Chuẩn bị asset và render video" + asset_note + "."})
    if not actions:
        actions.append({"workspace": "Overview", "text": "Không có hành động bắt buộc; dự án đã sẵn sàng."})

    candidates = [
        path for path in (output_dir / name for name, _label, _validator in REPORT_SPECS.values()) if path.exists()
    ] + [path for path in (audio_path, subtitle_path, video_path) if path]
    candidates += [path for path in output_dir.rglob("*") if path.is_file()] if output_dir.is_dir() else []
    last_updated = max((path.stat().st_mtime for path in candidates), default=None)

    return {
        "review": review,
        "workflow": workflow,
        "gate_summary": gate_summary(validation)["label"],
        "has_audio_quality": bool(reports.get("audio_quality")),
        "has_handoff": bool(reports.get("handoff")),
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
            ("Độ phủ chấm điểm", display_coverage(quality_summary.get("scoring_coverage_ratio"))),
            ("Vấn đề cần xử lý", str(defects + len(blockers) + len(review["issues"]) + len(asset_problems))),
            ("Câu lặp cần xem", str(repeated_sentences)),
        ],
        "pipeline": [
            ("Story", "Đạt" if production_ready else ("Cần xử lý" if validation else "Chưa có")),
            ("Audio", "Đạt" if delivery["passed"] else ("Đã render" if audio_path else "Chưa render")),
            ("Handoff", "Sẵn sàng" if delivery["ready"] else ("Cần xử lý" if reports.get("handoff") else "Chưa có")),
            ("Video", f"{ready_videos}/{len(video_deliveries)} đạt" if video_deliveries else ("Đã render" if video_path else ("Chờ asset" if audio_path else "Chưa sẵn sàng"))),
            ("Media đầu ra", "Đạt kiểm định" if completed else "Chưa đủ kiểm định"),
        ],
        "audio_delivery": {
            "ready": delivery["ready"],
            "passed": delivery["passed"],
            "cue_count": delivery["cue_count"],
            "segment_count": delivery["segment_count"],
            "duration": format_duration(delivery["duration_seconds"]),
            "checks": f"{delivery['checks_passed']}/{delivery['checks_total']}" if delivery["checks_total"] else "—",
            "artifacts": f"{sum(row['exists'] and row['size_matches'] for row in delivery['artifacts'])}/3",
            "issues": delivery["issues"],
        },
        "video_deliveries": video_deliveries,
        "image_assets": image_assets,
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
            f"Ảnh · {selected_aspect.title()}": f"{scene_count}/{required_scene_images}",
        },
        "resources": [
            ("Kịch bản", "Có dữ liệu" if story else "Thiếu", f"{int(metrics.get('total_words') or 0):,} từ" if metrics else "—", str(output_dir / "story.json") if story else ""),
            ("Audio", "Đạt" if delivery["passed"] else ("Hoàn tất" if audio_path else "Chưa render"), format_duration(delivery["duration_seconds"]) if delivery["duration_seconds"] else str(audio_summary.get("estimated_duration") or audio_summary.get("audio_format") or "—"), str(audio_path or "")),
            ("Phụ đề", "Hoàn tất" if subtitle_path else "Chưa có", f"{delivery['cue_count']:,} câu" if delivery["cue_count"] else str(audio_summary.get("segment_count") or "—"), str(subtitle_path or "")),
            ("Handoff", "Sẵn sàng" if delivery["ready"] else ("Cần kiểm tra" if reports.get("handoff") else "Chưa có"), f"{sum(row['exists'] and row['size_matches'] for row in delivery['artifacts'])}/3 tài nguyên", str(output_dir / "audio_video_handoff.json") if reports.get("handoff") else ""),
            *[(f"Ảnh · {aspect.title()}", "Đủ file" if item["count"] == item["expected"] else "Thiếu", f"{item['count']}/{item['expected']} ảnh", str(item["directory"])) for aspect, item in image_assets.items()
              if stage != "STAGE1" and not (stage == "STAGE2" and aspect == "portrait")],
            *[(f"Video · {item['label']}", "Đạt" if item["ready"] else "Cần kiểm tra", f"{item['resolution']} · {format_duration(item['duration'])}", str(item["video_path"] or "")) for item in video_deliveries],
            *([] if video_deliveries else [("Video", "Hoàn tất" if video_path else "Chưa render", str(video_summary.get("aspect") or "—"), str(video_path or ""))]),
        ],
        "actions": actions,
    }


def render_overview() -> None:
    import streamlit as st

    default_dir = str((Path.cwd() / "output").resolve())
    if OVERVIEW_DIRECTORY_KEY not in st.session_state:
        apply_project_directory(st.session_state, default_dir)

    def apply_typed_directory() -> None:
        try:
            apply_project_directory(st.session_state, st.session_state[OVERVIEW_DIRECTORY_KEY])
        except ValueError as exc:
            st.session_state["studio_project_directory_error"] = str(exc)

    directory_col, picker_col = st.columns([6, 1])
    output_text = directory_col.text_input(
        "Thư mục dữ liệu dự án",
        key=OVERVIEW_DIRECTORY_KEY,
        help="Đọc tự động dữ liệu dự án và cập nhật đường dẫn mặc định của Story, Audio và Video Studio.",
        on_change=apply_typed_directory,
    )
    picker_col.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
    picker_col.button(
        "Chọn thư mục",
        key="studio_choose_project_directory",
        width="stretch",
        on_click=choose_project_directory,
        args=(st.session_state,),
    )
    if st.session_state.get("studio_project_directory_error"):
        st.error(st.session_state["studio_project_directory_error"])
    else:
        st.caption("Đường dẫn mặc định của Story Studio, Audio Studio và Video Studio được đồng bộ theo thư mục này.")
    output_dir = Path(output_text.strip()).expanduser()
    reports, statuses = load_effective_package(output_dir, st.session_state)
    model = build_overview_model(reports, statuses, st.session_state, output_dir=output_dir)

    st.caption("TỔNG QUAN DỰ ÁN")
    st.subheader(model["project_label"])
    updated_label = f"Cập nhật {model['updated']}" if model["updated"] != "—" else ""
    subtitle = " · ".join(part for part in (model["series"], updated_label) if part)
    if subtitle:
        st.caption(subtitle)
    getattr(st, model["verdict_kind"])(f"**{model['verdict']}** · Dữ liệu tại `{model['output_dir']}`")
    render_workflow_summary(model["workflow"])

    st.subheader("Hành động ưu tiên")

    def open_workspace(workspace: str, story_section: str | None = None) -> None:
        st.session_state["studio_workspace"] = workspace
        if story_section:
            st.session_state["story_studio_section"] = story_section

    for index, action in enumerate(model["actions"]):
        text_col, button_col = st.columns([5, 1])
        text_col.markdown(f"- {action['text']}")
        if action["workspace"] != "Overview":
            story_section = action.get("section")
            if action["workspace"] == "Story Studio" and not story_section:
                if "Bổ sung dữ liệu" in action["text"]:
                    story_section = "Tổng quan"
                elif "Video đầu ra" in action["text"]:
                    story_section = "Video đầu ra"
                elif "Lặp câu" in action["text"]:
                    story_section = "Nội dung"
                elif "Âm thanh & phụ đề" in action["text"]:
                    story_section = "Âm thanh & phụ đề"
            button_col.button(
                f"Mở {action['workspace']}",
                key=f"overview_action_{index}",
                on_click=open_workspace,
                args=(action["workspace"], story_section),
            )

    render_source_provenance(output_dir, reports, statuses)
    columns = [*st.columns(4), *st.columns(3)]
    for column, (label, value) in zip(columns, model["metrics"]):
        column.metric(label, value)

    st.caption(model["gate_summary"] + " · Số cảnh do báo cáo khai báo; không phải số ảnh sản xuất.")
    st.subheader("Sản xuất audio/video · độc lập với stage gói truyện")
    pipeline_columns = st.columns(len(model["pipeline"]))
    for index, (column, (label, status)) in enumerate(zip(pipeline_columns, model["pipeline"]), start=1):
        icon = "✓" if status in {"Đạt", "Đã render", "Sẵn sàng"} else ("!" if status in {"Cần xử lý", "Chờ asset"} else "○")
        column.markdown(f"**{index}. {label}**  \n{icon} {status}")

    st.subheader("Audio & Phụ đề")
    delivery = model["audio_delivery"]
    delivery_columns = st.columns(4)
    delivery_values = (
        ("Bàn giao Audio → Video", "Sẵn sàng" if delivery["ready"] else ("Cần kiểm tra" if model["has_handoff"] else "Chưa tạo")),
        ("Chất lượng Audio", "Đạt" if delivery["passed"] else ("Chưa đạt" if model["has_audio_quality"] else "Chưa kiểm định")),
        ("Phụ đề", f"{delivery['cue_count']:,} câu · {delivery['duration']}" if delivery["cue_count"] else "Chưa có"),
        ("Tính toàn vẹn", f"{delivery['artifacts']} tệp hợp lệ"),
    )
    for column, (label, value) in zip(delivery_columns, delivery_values):
        column.metric(label, value)
    if delivery["issues"]:
        st.warning(" · ".join(delivery["issues"]))

    st.subheader("Video đầu ra")
    video_deliveries = model["video_deliveries"]
    if not video_deliveries:
        st.info("Chưa phát hiện result manifest hoặc báo cáo chất lượng video.")
    else:
        video_columns = st.columns(min(4, len(video_deliveries)))
        for column, item in zip(video_columns, video_deliveries):
            with column:
                st.markdown(f"**{item['label']}**")
                st.metric("Trạng thái", "Sẵn sàng" if item["ready"] else "Cần kiểm tra")
                st.caption(f"{item['resolution']} · {format_duration(item['duration'])} · {item['size']}")
                if item["failed_checks"]:
                    st.caption(f"{len(item['failed_checks'])} kiểm tra chưa đạt")

    st.subheader("Hình ảnh dự án")
    for column, group in zip(st.columns(3), ("characters", "landscape", "portrait")):
        assets = [row for row in model["review"]["assets"] if row["group"] == group]
        column.metric({"characters": "Nhân vật", "landscape": "Landscape", "portrait": "Portrait"}[group],
                      f"{sum(bool(row['sha256']) and not row['issues'] for row in assets)}/{len(assets)} ảnh hợp lệ")
    st.button("Mở tài nguyên", on_click=open_workspace, args=("Story Studio", "Tài nguyên"))
    render_aspect_cover_gallery(output_dir, key_prefix="overview_cover")

    with st.expander("Thông số sản xuất", expanded=False):
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




__all__ = ["build_overview_model", "render_overview"]
