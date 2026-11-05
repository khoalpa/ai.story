"""Project-level dashboard for the unified Studio workspace."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from studio.audio_delivery_report import format_duration, inspect_audio_delivery
from studio.navigation import navigate_to
from studio.package_quality_report import _items, _object
from studio.project_context import (
    OVERVIEW_DIRECTORY_KEY,
    apply_project_directory,
    choose_project_directory,
    project_directory_has_files,
)
from studio.project_review import required_report_keys, review_package
from studio.story_images import (
    inspect_story_images,
    render_aspect_cover_gallery,
    stage_applicable_aspects,
    visual_plan_image_stems,
)
from studio.story_repetition import analyze_story_repetition
from studio.story_studio import (
    REPORT_SPECS,
    load_effective_package,
    render_source_provenance,
)
from studio.ui_components import render_empty_state
from studio.video_delivery_report import (
    build_video_delivery_summary,
    quality_failure_reasons,
)
from studio.workflow_builder import (
    complete_stage_atomic,
    plan_stage_completion,
    restore_integrity_backup,
)
from studio.workflow_views import render_manifest_repair, render_workflow_summary

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def workflow_verdict(status: str) -> tuple[str, str]:
    """Map a verified workflow status to its overview message and Streamlit call."""
    return {
        "PASS": ("Gói đạt các phép kiểm tra đã chạy", "success"),
        "PARTIAL": ("Gói đã kiểm định nhưng chưa hoàn tất", "warning"),
        "FAIL": ("Gói có lỗi cần xử lý", "error"),
        "NOT_VERIFIED": ("Gói chưa được xác minh đầy đủ", "warning"),
    }.get(status, ("Gói chưa được xác minh đầy đủ", "warning"))


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


def _persisted_audio_summary(reports: Mapping[str, Any]) -> dict[str, Any]:
    quality = _object(reports.get("audio_quality"))
    if not quality:
        return {}
    target = _object(quality.get("target"))
    pacing = _object(quality.get("pacing"))
    mix = _object(quality.get("mix"))
    segments = _object(quality.get("segments"))
    audio_file = str(quality.get("audio_file") or "")
    loudness = " · ".join(
        part for part in (
            f"{target['integrated_lufs']:g} LUFS" if type(target.get("integrated_lufs")) in {int, float} else "",
            f"{target['true_peak_dbtp']:g} dBTP" if type(target.get("true_peak_dbtp")) in {int, float} else "",
        ) if part
    )
    values = {
        "audio_format": Path(audio_file).suffix.lstrip(".") or None,
        "pacing_preset": pacing.get("preset"),
        "loudness_profile": loudness or quality.get("profile"),
        "bgm": "Bật" if mix.get("bgm_ducking_enabled") is True else "Tắt" if mix.get("bgm_ducking_enabled") is False else None,
        "segment_count": segments.get("measured_count"),
    }
    return {key: value for key, value in values.items() if value is not None}


def _persisted_video_summary(variants: Any, preferred_aspect: Any) -> dict[str, Any]:
    if not isinstance(variants, Mapping) or not variants:
        return {}
    preferred = _video_aspect_name(preferred_aspect)
    name, reports = next(
        ((name, value) for name, value in variants.items() if preferred in str(name).casefold()),
        next(iter(variants.items())),
    )
    quality = _object(_object(reports).get("quality"))
    stream = _object(quality.get("video_stream"))
    subtitle = _object(quality.get("subtitle"))
    if not quality:
        return {}
    aspect = stream.get("display_aspect_ratio")
    fps = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    if isinstance(fps, str) and fps.endswith("/1") and fps[:-2].isdigit():
        fps = int(fps[:-2])
    codec = str(stream.get("codec_name") or "").upper()
    profile = str(stream.get("profile") or "")
    pixel_format = str(stream.get("pix_fmt") or "")
    encoding = " · ".join(part for part in (codec, profile, pixel_format) if part)
    values = {
        "aspect": aspect or ("9:16" if "portrait" in str(name).casefold() else "16:9"),
        "encoding_profile": encoding or None,
        "video_fps": fps,
        "show_subtitles": subtitle.get("present") if "present" in subtitle else None,
    }
    return {key: value for key, value in values.items() if value is not None}


def _validation_counts(validation: Mapping[str, Any]) -> tuple[int, int, int]:
    checks = _items(validation.get("checks"))
    passed = sum(row.get("status") in {"PASS", "NOT_APPLICABLE"} for row in checks)
    failed = sum(row.get("status") == "FAIL" for row in checks)
    return passed, failed, len(checks)


def _story_word_count(story: Mapping[str, Any]) -> int:
    return sum(len(str(row.get("text") or "").split()) for row in _items(story.get("script")))


def _package_versions(reports: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return version metadata declared by the selected story package."""
    manifest = _object(reports.get("workflow"))
    validation = _object(reports.get("validation"))
    story = _object(reports.get("story"))
    image_prompts = _object(reports.get("image_prompts"))
    return [
        ("prompt_version", str(manifest.get("prompt_version") or validation.get("prompt_version") or "—")),
        ("schema_version", str(manifest.get("schema_version") or story.get("schema_version") or "—")),
        ("image_prompt_version", str(image_prompts.get("image_prompt_version") or "—")),
    ]

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
    anchor = _object(reports.get("anchor"))
    meta = _object(story.get("meta"))
    continuity = _object(anchor.get("continuity"))
    passed_checks, failed_checks, total_checks = _validation_counts(validation)
    limitations = _items(validation.get("limitations"))
    remaining_work = _items(validation.get("remaining_work"))
    repetition = analyze_story_repetition(story) if story else {"summary": {}}
    repetition_summary = _object(repetition.get("summary"))
    repetition_pairs = int(repetition_summary.get("pair_count") or 0)
    repeated_sentences = int(repetition_summary.get("affected_sentence_count") or 0)
    image_assets = inspect_story_images(output_dir)

    # The settings snapshots make this section useful before a render and keep
    # it populated when Streamlit stops rendering the workspace-owned widgets.
    # A completed run remains authoritative for fields captured at render time.
    audio_summary = {
        **_persisted_audio_summary(reports),
        **_object(state.get("audio_production_settings")),
        **_object(state.get("last_result_summary")),
    }
    video_variants = reports.get("video_deliveries")
    video_summary = {
        **_persisted_video_summary(video_variants, _object(state.get("video_production_settings")).get("aspect") or state.get("video_aspect")),
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
    video_deliveries = build_video_delivery_summary(
        video_variants if isinstance(video_variants, Mapping) else {}, output_dir
    )
    manifest_video = next((item["video_path"] for item in video_deliveries if item["video_path"]), None)
    video_path = video_path or manifest_video
    for item in video_deliveries:
        item["ready"] = item["ready"] and not item["failed_checks"]
    ready_videos = sum(item["ready"] for item in video_deliveries)
    failed_video_deliveries = [item for item in video_deliveries if not item["ready"]]
    failed_video_labels = ", ".join(item["label"] for item in failed_video_deliveries)
    video_failure_details = [
        {
            "label": item["label"],
            "reasons": (
                quality_failure_reasons(item) + [
                    issue for issue in item["issues"]
                    if "phép kiểm tra chất lượng chưa đạt" not in issue
                ]
                if item["failed_checks"] or item["issues"]
                else ["Video chưa đáp ứng đầy đủ điều kiện bàn giao."]
            ),
        }
        for item in failed_video_deliveries
    ]
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
        active_stems = visual_plan_image_stems(output_dir)
        scene_count = sum(stem in available_stems for stem in active_stems)
        required_scene_images = len(active_stems)
    outline = story.get("outline")
    expected_scenes = len(outline) if isinstance(outline, (list, dict)) else 0

    review = review_package(output_dir, reports, statuses, state)
    workflow = review["workflow"]
    stage = workflow["stage"]
    production_ready = review["story_ready"]
    completed = bool(delivery["ready"] and delivery["passed"] and video_deliveries and ready_videos == len(video_deliveries))
    workflow_status = workflow.get("overall_status", workflow.get("status", "NOT_VERIFIED"))
    if not story and not validation and not reports.get("workflow"):
        verdict = "Chưa đủ dữ liệu"
        verdict_kind = "warning"
    elif workflow_status == "FAIL":
        verdict, verdict_kind = workflow_verdict(workflow_status)
    elif stage and workflow_status in {"PASS", "PARTIAL", "NOT_VERIFIED"}:
        verdict, verdict_kind = workflow_verdict(workflow_status)
    elif failed_checks or remaining_work or review["issues"] or (validation and not production_ready):
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

    title = str(meta.get("title") or "Dự án chưa đặt tên")
    episode = meta.get("episode") or continuity.get("latest_episode")
    series = str(meta.get("series") or _object(anchor.get("series")).get("title") or "")
    project_label = title + (f" · Tập {episode}" if episode not in {None, ""} else "")
    missing = [
        label
        for key, (_filename, label, _validator) in REPORT_SPECS.items()
        if statuses.get(key) == "Thiếu" and key in required_report_keys(reports)
    ]

    failed_workflow_checks = [
        row for row in _items(workflow.get("checks"))
        if row.get("status") == "FAIL"
    ]
    workflow_issue_texts = {
        f"{row.get('check')}: {row.get('detail')}"
        for row in failed_workflow_checks
    }
    actions: list[dict[str, str]] = [
        {"workspace": "Story Studio", "section": issue["section"], "text": issue["text"]}
        for issue in review["issues"]
        if not str(issue.get("text", "")).startswith("stage_gates:")
        and str(issue.get("text", "")) not in workflow_issue_texts
    ]
    integrity_status = workflow.get("integrity_status", "NOT_VERIFIED")
    completion_status = workflow.get("package_completion_status") or _object(workflow.get("manifest")).get("status")
    stage_gate_status = workflow.get("stage_gate_status", "NOT_VERIFIED")
    workflow_blockers: list[dict[str, str]] = []
    if stage and integrity_status == "FAIL":
        failure_details = "; ".join(
            str(row.get("detail"))
            for row in failed_workflow_checks
            if row.get("detail")
        )
        detail_label = f" Nguyên nhân: {failure_details}" if failure_details else ""
        workflow_blockers.append({"workspace": "Story Studio", "section": "Gói & quy trình",
                                  "text": "Manifest hoặc file trong gói không còn đồng bộ. "
                                          "Mở Gói & quy trình, xem trước thay đổi, tạo bản sao lưu "
                                          f"và sửa tính toàn vẹn trước khi tiếp tục.{detail_label}"})
    if stage and completion_status and completion_status != "COMPLETE" and stage_gate_status == "PASS":
        workflow_blockers.append({"workspace": "Story Studio", "section": "Gói & quy trình",
                                  "text": f"Hoàn tất Stage hiện tại: manifest đang ở trạng thái {completion_status}."})
    if stage and stage_gate_status != "PASS" and integrity_status != "FAIL":
        unresolved_gates = [
            str(row.get("id") or "UNKNOWN")
            for row in _items(validation.get("checks"))
            if row.get("required") is True and row.get("status") not in {"PASS", "NOT_APPLICABLE"}
        ]
        gate_label = ", ".join(unresolved_gates) if unresolved_gates else stage_gate_status
        remaining_label = f" · {len(remaining_work)} đầu việc còn lại" if remaining_work else ""
        workflow_blockers.append({"workspace": "Story Studio", "section": "Kiểm định",
                                  "text": f"Hoàn tất kiểm định {stage}: {gate_label}{remaining_label}."})
    actions = workflow_blockers + actions
    if story and not stage:
        actions.insert(0, {"workspace": "Story Studio", "section": "Gói & quy trình", "text": "Mở story.zip để kiểm tra manifest; không suy stage từ thư mục hoặc tên file."})
    asset_problems = review["asset_issues"] if story else []
    if asset_problems:
        examples = "; ".join(f"{row['name']}: {row['status']}" for row in asset_problems[:3])
        actions.append({"workspace": "Story Studio", "section": "Tài nguyên", "text": f"{len(asset_problems)} ảnh cần kiểm tra · {examples}"})
    if missing:
        actions.append({"workspace": "Story Studio", "text": "Bổ sung dữ liệu: " + ", ".join(missing) + "."})
    if failed_checks and (not stage or stage_gate_status == "PASS"):
        actions.append({"workspace": "Story Studio", "section": "Kiểm định", "text": f"Xử lý {failed_checks} phép kiểm tra chưa đạt."})
    if remaining_work and (not stage or stage_gate_status == "PASS"):
        actions.append({"workspace": "Story Studio", "section": "Kiểm định", "text": f"Hoàn tất {len(remaining_work)} đầu việc còn lại trong validation_report.json."})
    if repetition_pairs:
        actions.append({
            "workspace": "Story Studio",
            "text": f"Xem lại {repetition_pairs} cặp câu lặp hoặc gần trùng trong Nội dung → Lặp câu.",
        })
    package_blocked = bool(workflow_blockers)
    if stage in {"STAGE1", "STAGE2"}:
        actions.append({"workspace": "Story Studio", "section": "Gói & quy trình", "text": "Hoàn tất kiểm định gói hiện tại trước khi chuyển stage thủ công; chưa yêu cầu render audio/video."})
    elif package_blocked:
        pass
    elif not audio_path:
        actions.append({"workspace": "Audio Studio", "text": "Render audio và phụ đề từ kịch bản."})
    elif reports.get("audio_quality") and not delivery["passed"]:
        actions.append({"workspace": "Story Studio", "text": "Mở Âm thanh & phụ đề và xử lý các phép kiểm tra audio chưa đạt."})
    elif delivery["issues"]:
        actions.append({"workspace": "Story Studio", "text": delivery["issues"][0]})
    elif video_deliveries and ready_videos < len(video_deliveries):
        actions.append({
            "workspace": "Story Studio",
            "section": "Video đầu ra",
            "text": f"Video chưa đạt: {failed_video_labels}. Mở kết quả để xem lý do và kiểm tra lại.",
        })
    elif not video_path:
        asset_note = ""
        if required_scene_images and scene_count < required_scene_images:
            asset_note = f"; hiện có {scene_count}/{required_scene_images} ảnh {selected_aspect}"
        actions.append({"workspace": "Video Studio", "text": "Chuẩn bị asset và render video" + asset_note + "."})
    if not actions:
        actions.append({"workspace": "Overview", "text": "Không có hành động bắt buộc; dự án đã sẵn sàng."})

    for index, action in enumerate(actions):
        action["severity"] = (
            "blocking" if index < len(workflow_blockers)
            else "warning" if action.get("workspace") != "Overview"
            else "info"
        )

    candidates = [
        path for path in (output_dir / name for name, _label, _validator in REPORT_SPECS.values()) if path.exists()
    ] + [path for path in (audio_path, subtitle_path, video_path) if path]
    candidates += [path for path in output_dir.rglob("*") if path.is_file()] if output_dir.is_dir() else []
    last_updated = max((path.stat().st_mtime for path in candidates), default=None)

    estimated_minutes = meta.get("estimated_minutes")
    duration_label = f"{estimated_minutes:.1f} phút" if type(estimated_minutes) is int or type(estimated_minutes) is float else "—"
    return {
        "review": review,
        "workflow": workflow,
        "gate_summary": (f"{passed_checks}/{total_checks} phép kiểm tra đạt hoặc không áp dụng"
                         if total_checks else "Chưa có validation_report.json được hỗ trợ"),
        "has_audio_quality": bool(reports.get("audio_quality")),
        "has_handoff": bool(reports.get("handoff")),
        "project_label": project_label,
        "series": series,
        "output_dir": str(output_dir.resolve()),
        "verdict": verdict,
        "verdict_kind": verdict_kind,
        "updated": datetime.fromtimestamp(last_updated).strftime("%d/%m/%Y %H:%M") if last_updated else "—",
        "package_versions": _package_versions(reports),
        "metrics": [
            ("Thời lượng dự kiến", duration_label),
            ("Số từ", f"{_story_word_count(story):,}" if story else "—"),
            ("Số cảnh", str(expected_scenes) if expected_scenes else "—"),
            ("Kiểm định", f"{passed_checks}/{total_checks}" if total_checks else "—"),
            ("Trạng thái báo cáo", str(validation.get("status") or "—")),
            ("Giới hạn đã ghi nhận", str(len(limitations))),
            ("Vấn đề cần xử lý", str(failed_checks + len(remaining_work) + len(review["issues"]) + len(asset_problems))),
            ("Câu lặp cần xem", str(repeated_sentences)),
        ],
        "pipeline": [
            ("Story", "Đạt" if production_ready else ("Cần xử lý" if validation else "Chưa có")),
            ("Audio", "Đạt" if delivery["passed"] else ("Đã render" if audio_path else "Chưa render")),
            ("Handoff", "Sẵn sàng" if delivery["ready"] else ("Cần xử lý" if reports.get("handoff") else "Chưa có")),
            ("Video", f"{ready_videos}/{len(video_deliveries)} đạt" if video_deliveries else ("Đã render" if video_path else ("Chờ asset" if audio_path else "Chưa sẵn sàng"))),
            ("Media đầu ra", "Đạt kiểm định" if completed else "Chưa đủ kiểm định"),
        ],
        "progress_pipeline": [
            ("Nội dung", "Đạt" if story else "Chưa có"),
            ("Kiểm định", f"{passed_checks}/{total_checks} đạt" if total_checks and not failed_checks else (f"{failed_checks} lỗi" if failed_checks else "Chưa có")),
            ("Audio", "Đạt" if delivery["passed"] else ("Đã render" if audio_path else "Chưa render")),
            ("Hình ảnh", f"{scene_count}/{required_scene_images}" if required_scene_images else "Chưa áp dụng"),
            ("Video", f"{ready_videos}/{len(video_deliveries)} đạt" if video_deliveries else ("Đã render" if video_path else ("Chờ asset" if audio_path else "Chưa sẵn sàng"))),
        ],
        "progress_states": [
            {
                "label": "Nội dung", "status": "Đạt" if story else "Chưa có",
                "tone": "success" if story else "neutral", "reason": "" if story else "Chưa có nội dung truyện.",
            },
            {
                "label": "Kiểm định",
                "status": f"{passed_checks}/{total_checks} đạt" if total_checks and not failed_checks else (f"{failed_checks} lỗi" if failed_checks else "Chưa có"),
                "tone": "success" if total_checks and not failed_checks else ("error" if failed_checks else "neutral"),
                "reason": f"{failed_checks} phép kiểm tra chưa đạt." if failed_checks else ("Chưa có dữ liệu kiểm định." if not total_checks else ""),
            },
            {
                "label": "Audio", "status": "Đạt" if delivery["passed"] else ("Đã render" if audio_path else "Chưa render"),
                "tone": "success" if delivery["passed"] else ("warning" if audio_path else "neutral"),
                "reason": "" if delivery["passed"] else (delivery["issues"][0] if delivery["issues"] else "Audio chưa được kiểm định."),
            },
            {
                "label": "Hình ảnh", "status": f"{scene_count}/{required_scene_images}" if required_scene_images else "Chưa áp dụng",
                "tone": "success" if required_scene_images and scene_count >= required_scene_images else ("warning" if required_scene_images else "neutral"),
                "reason": (f"Thiếu {required_scene_images - scene_count} ảnh {selected_aspect}." if required_scene_images and scene_count < required_scene_images else ""),
            },
            {
                "label": "Video",
                "status": f"{ready_videos}/{len(video_deliveries)} đạt" if video_deliveries else ("Đã render" if video_path else ("Chờ asset" if audio_path else "Chưa sẵn sàng")),
                "tone": "success" if video_deliveries and ready_videos == len(video_deliveries) else ("warning" if video_deliveries or video_path else "neutral"),
                "reason": f"Chưa đạt: {failed_video_labels}." if failed_video_labels else ("Chưa có video đầu ra để kiểm tra." if not video_path else "Video chưa có báo cáo kiểm định."),
            },
        ],
        "video_failure_details": video_failure_details,
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
            ("Kịch bản", "Có dữ liệu" if story else "Thiếu", f"{_story_word_count(story):,} từ" if story else "—", str(output_dir / "story.json") if story else ""),
            ("Audio", "Đạt" if delivery["passed"] else ("Hoàn tất" if audio_path else "Chưa render"), format_duration(delivery["duration_seconds"]) if delivery["duration_seconds"] else str(audio_summary.get("estimated_duration") or audio_summary.get("audio_format") or "—"), str(audio_path or "")),
            ("Phụ đề", "Hoàn tất" if subtitle_path else "Chưa có", f"{delivery['cue_count']:,} câu" if delivery["cue_count"] else str(audio_summary.get("segment_count") or "—"), str(subtitle_path or "")),
            ("Handoff", "Sẵn sàng" if delivery["ready"] else ("Cần kiểm tra" if reports.get("handoff") else "Chưa có"), f"{sum(row['exists'] and row['size_matches'] for row in delivery['artifacts'])}/3 tài nguyên", str(output_dir / "audio_video_handoff.json") if reports.get("handoff") else ""),
            *[(f"Ảnh · {aspect.title()}", "Đủ file" if item["count"] == item["expected"] else "Thiếu", f"{item['count']}/{item['expected']} ảnh", str(item["directory"])) for aspect, item in image_assets.items()
              if stage != "STAGE1" and not (stage == "STAGE2" and aspect == "portrait")],
            *[(f"Video · {item['label']}", "Đạt" if item["ready"] else "Cần kiểm tra", f"{item['resolution']} · {format_duration(item['duration'])}", str(item["video_path"] or "")) for item in video_deliveries],
            *([] if video_deliveries else [("Video", "Hoàn tất" if video_path else "Chưa render", str(video_summary.get("aspect") or "—"), str(video_path or ""))]),
        ],
        "actions": actions,
        "primary_action": actions[0],
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

    with st.expander("Đổi dự án", expanded=False):
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
            st.caption("Story Studio, Audio Studio và Video Studio dùng chung thư mục này.")
    output_dir = Path(output_text.strip()).expanduser()
    if output_dir.is_dir() and not project_directory_has_files(output_dir):
        st.caption("TỔNG QUAN DỰ ÁN")
        render_empty_state(
            "Thư mục dự án đang trống",
            "Chưa có dữ liệu dự án trong thư mục này. Hãy chọn thư mục đã chứa dữ liệu hoặc tạo nội dung trong Story Studio để bắt đầu.",
            icon="○",
        )
        return
    reports, statuses = load_effective_package(output_dir, st.session_state)
    model = build_overview_model(reports, statuses, st.session_state, output_dir=output_dir)

    st.caption("TỔNG QUAN DỰ ÁN")
    title_col, stage_col = st.columns([5, 1])
    title_col.subheader(model["project_label"])
    stage = model["workflow"].get("stage")
    if stage:
        stage_col.metric("Giai đoạn", str(stage).replace("STAGE", "Stage "))
    updated_label = f"Cập nhật {model['updated']}" if model["updated"] != "—" else ""
    subtitle = " · ".join(part for part in (model["series"], updated_label) if part)
    if subtitle:
        st.caption(subtitle)
    version_labels = {
        "prompt_version": "Prompt",
        "schema_version": "Schema",
        "image_prompt_version": "Image Prompt",
    }
    version_summary = " · ".join(
        f"{version_labels.get(name, name)} {value}"
        for name, value in model["package_versions"]
    )
    st.caption(version_summary)
    primary_action = model["primary_action"]
    getattr(st, model["verdict_kind"])(f"**{model['verdict']}**  \n{primary_action['text']}")
    st.subheader("Việc cần làm tiếp theo")

    completion_backup_key = f"overview_completion_backup_{output_dir.resolve()}"
    completion_feedback_key = f"overview_completion_feedback_{output_dir.resolve()}"
    if feedback := st.session_state.pop(completion_feedback_key, None):
        (st.success if feedback[0] == "success" else st.error)(feedback[1])
    if backup_value := st.session_state.get(completion_backup_key):
        st.success("Stage đã được hoàn tất và hậu kiểm thành công. Bản sao lưu vẫn còn để hoàn tác.")
        if st.button("Hoàn tác hoàn tất Stage", key=f"overview_completion_undo_{output_dir.resolve()}"):
            try:
                restore_integrity_backup(output_dir, Path(str(backup_value)))
            except (OSError, ValueError) as exc:
                st.session_state[completion_feedback_key] = ("error", f"Hoàn tác thất bại: {exc}")
            else:
                st.session_state.pop(completion_backup_key, None)
                st.session_state[completion_feedback_key] = ("success", "Đã khôi phục trạng thái PARTIAL trước đó.")
            st.rerun()

    completion_plan = None
    if (
        model["workflow"].get("integrity_status") == "PASS"
        and model["workflow"].get("stage_gate_status") == "PASS"
        and model["workflow"].get("package_completion_status") != "COMPLETE"
    ):
        try:
            completion_plan = plan_stage_completion(output_dir)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            st.error(f"Không thể phân tích bước hoàn tất Stage: {exc}")
    if completion_plan is not None:
        st.info("Gói đã đủ bằng chứng để đóng Stage. Thao tác sẽ cập nhật report, manifest và ZIP checkpoint theo giao dịch nguyên tử.")
        with st.expander("Xem trước hoàn tất Stage", expanded=True):
            for change in completion_plan.get("changes", []):
                st.markdown(f"- {change}")
            for blocker in completion_plan.get("blockers", []):
                st.error(blocker)
        if st.button(
            f"Xác minh và hoàn tất {model['workflow'].get('stage', 'Stage')}",
            type="primary", disabled=not completion_plan.get("can_complete"),
            key=f"overview_complete_stage_{output_dir.resolve()}",
        ):
            try:
                inspection, backup = complete_stage_atomic(output_dir)
                if inspection.get("publish_status") != "PASS":
                    raise ValueError("Hậu kiểm cuối chưa đạt publish PASS")
            except (OSError, KeyError, TypeError, ValueError) as exc:
                st.session_state[completion_feedback_key] = ("error", f"Không thể hoàn tất Stage: {exc}")
            else:
                st.session_state[completion_backup_key] = str(backup)
                st.session_state[completion_feedback_key] = (
                    "success", "Stage đã COMPLETE; manifest, report và checkpoint đã được hậu kiểm."
                )
            st.rerun()

    def open_workspace(workspace: str, story_section: str | None = None) -> None:
        navigate_to(st.session_state, workspace, story_section=story_section)

    visible_actions = [
        action for action in model["actions"]
        if not (str(action.get("text", "")).startswith("Hoàn tất Stage hiện tại:") and completion_plan is not None)
    ]
    for index, action in enumerate(visible_actions[:3]):
        text_col, button_col = st.columns([8, 1], vertical_alignment="center")
        text_col.markdown(f"**{index + 1}.** {action['text']}")
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
                "Mở",
                key=f"overview_action_{index}",
                on_click=open_workspace,
                args=(action["workspace"], story_section),
                width="stretch",
            )
    if len(visible_actions) > 3:
        with st.expander(f"Xem thêm {len(visible_actions) - 3} việc"):
            for action in visible_actions[3:]:
                st.markdown(f"- {action['text']}")

    st.markdown("**Sức khỏe dự án**")
    health_columns = st.columns(4)
    for column, (label, value) in zip(health_columns, (
        ("Kiểm định", model["metrics"][3][1]),
        ("Vấn đề", model["metrics"][6][1]),
        ("Câu lặp", model["metrics"][7][1]),
        ("Cập nhật", model["updated"]),
    )):
        column.metric(label, value)

    st.subheader("Tiến độ sản xuất")
    progress_states = model["progress_states"]
    pipeline_columns = st.columns(len(progress_states))
    progress_icons = {"success": "✓", "warning": "!", "error": "✕", "neutral": "○"}
    for index, (column, progress) in enumerate(zip(pipeline_columns, progress_states), start=1):
        icon = progress_icons[progress["tone"]]
        column.markdown(f"**{index}. {progress['label']}**  \n{icon} {progress['status']}")
        if progress["reason"]:
            column.caption(progress["reason"])

    video_failure_details = model["video_failure_details"]
    if video_failure_details:
        with st.expander(f"Xem chi tiết lý do Video chưa đạt ({len(video_failure_details)})"):
            for detail in video_failure_details:
                st.markdown(f"**{detail['label']}**")
                for reason in detail["reasons"]:
                    st.markdown(f"- {reason}")

    st.subheader("Đầu ra gần nhất")
    delivery = model["audio_delivery"]
    video_deliveries = model["video_deliveries"]
    applicable_aspects = stage_applicable_aspects(model["workflow"]["stage"])
    asset_rows = [row for row in model["review"]["assets"] if row["group"] in applicable_aspects or row["group"] == "characters"]
    valid_assets = sum(bool(row["sha256"]) and not row["issues"] for row in asset_rows)
    output_columns = st.columns(3)
    with output_columns[0]:
        st.markdown("**Audio & phụ đề**")
        st.metric("Trạng thái", "Đạt" if delivery["passed"] else ("Cần kiểm tra" if model["has_audio_quality"] else "Chưa kiểm định"))
        st.caption(f"{delivery['duration']} · {delivery['cue_count']:,} câu phụ đề" if delivery["cue_count"] else "Chưa có phụ đề")
        st.button("Mở âm thanh", on_click=open_workspace, args=("Audio Studio", None), width="stretch")
    with output_columns[1]:
        st.markdown("**Hình ảnh**")
        st.metric("Tài nguyên hợp lệ", f"{valid_assets}/{len(asset_rows)}" if asset_rows else "Chưa có")
        st.caption("Ảnh nhân vật và ảnh cảnh áp dụng cho Stage hiện tại")
        st.button("Mở tài nguyên", on_click=open_workspace, args=("Story Studio", "Tài nguyên"), width="stretch")
    with output_columns[2]:
        st.markdown("**Video**")
        ready_video_count = sum(item["ready"] for item in video_deliveries)
        st.metric("Trạng thái", f"{ready_video_count}/{len(video_deliveries)} đạt" if video_deliveries else "Chưa render")
        st.caption(" · ".join(item["label"] for item in video_deliveries) if video_deliveries else "Chưa có MP4 được kiểm định")
        st.button("Mở Video Studio", on_click=open_workspace, args=("Video Studio", None), width="stretch")
    if delivery["issues"]:
        st.warning("Audio: " + " · ".join(delivery["issues"]))

    with st.expander("Chỉ số bổ sung"):
        metric_columns = st.columns(4)
        for column, (label, value) in zip(metric_columns, model["metrics"][:4]):
            column.metric(label, value)
        st.caption(model["gate_summary"] + " · Số cảnh lấy từ outline; không phải số ảnh sản xuất.")

    with st.expander("Quy trình và bằng chứng kiểm định", expanded=False):
        render_workflow_summary(model["workflow"])
        render_manifest_repair(output_dir, model["workflow"])
        source_comparison = model["workflow"].get("source_comparison")
        if source_comparison:
            (st.success if source_comparison["status"] == "PASS" else st.error)(source_comparison["detail"])
        render_source_provenance(output_dir, reports, statuses)
        render_aspect_cover_gallery(output_dir, key_prefix="overview_cover", stage=model["workflow"]["stage"])

    with st.expander("Thông số sản xuất", expanded=False):
        audio_col, video_col = st.columns(2)
        for column, heading, values in ((audio_col, "Audio", model["audio"]), (video_col, "Video", model["video"])):
            with column:
                st.markdown(f"**{heading}**")
                st.table([{"Thông số": key, "Giá trị": value} for key, value in values.items()])
    
    with st.expander("Tài nguyên, đường dẫn và trạng thái kỹ thuật", expanded=False):
        st.caption("PHIÊN BẢN GÓI TRUYỆN")
        for column, (label, value) in zip(st.columns(3), model["package_versions"]):
            column.metric(label, value)
        st.dataframe(
            [{"Thành phần": name, "Trạng thái": status, "Thông tin": info, "Đường dẫn": path} for name, status, info, path in model["resources"]],
            width="stretch",
            hide_index=True,
        )




__all__ = ["build_overview_model", "render_overview"]
