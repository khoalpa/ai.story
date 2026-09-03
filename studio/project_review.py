"""Shared package assessment for both Studio summaries."""
from pathlib import Path
from typing import Any, Mapping

from studio.package_quality_report import _items, _object
from studio.project_assets import inspect_project_assets, inspect_report_bindings
from studio.report_semantics import gate_issues, gate_summary, series_required
from studio.video_prompt_validation import validate_video_prompt_plan
from studio.workflow_package import (
    STAGES,
    inspect_directory,
    inspect_members,
    read_archive,
)

VERIFICATION_SOURCE_KEY = "story_verification_source"
VERIFICATION_ROOT_KEY = "story_verification_root"
VERIFICATION_UPLOAD_BYTES_KEY = "story_verification_upload_bytes"
DIRECTORY_SOURCE = "DIRECTORY"
LOCAL_ZIP_SOURCE = "LOCAL_ZIP"
UPLOADED_ZIP_SOURCE = "UPLOADED_ZIP"
VERIFICATION_SOURCE_LABELS = {
    DIRECTORY_SOURCE: "Thư mục đang mở",
    LOCAL_ZIP_SOURCE: "story.zip trong thư mục",
    UPLOADED_ZIP_SOURCE: "ZIP đã tải lên",
}


def selected_verification_source(root: Path, state: Mapping[str, Any]) -> str:
    if state.get(VERIFICATION_ROOT_KEY) != str(root.resolve()):
        return DIRECTORY_SOURCE
    source = str(state.get(VERIFICATION_SOURCE_KEY) or DIRECTORY_SOURCE)
    return source if source in VERIFICATION_SOURCE_LABELS else DIRECTORY_SOURCE


def verification_source_label(root: Path, state: Mapping[str, Any]) -> str:
    source = selected_verification_source(root, state)
    return VERIFICATION_SOURCE_LABELS[source]


def inspect_selected_workflow(root: Path, state: Mapping[str, Any], *, overridden: bool = False,
                              parent: Mapping[str, bytes] | None = None) -> dict[str, Any]:
    """Inspect the shared verification source and compare ZIP bytes with the content directory."""
    source = selected_verification_source(root, state)
    directory_result = inspect_directory(root, overridden=overridden, parent=parent)
    if source == DIRECTORY_SOURCE:
        directory_result["verification_source"] = source
        directory_result["source_comparison"] = None
        return directory_result

    zip_source: Path | bytes
    if source == LOCAL_ZIP_SOURCE:
        zip_source = root / "story.zip"
        if not zip_source.is_file():
            result = dict(directory_result)
            result.update(status="NOT_VERIFIED", integrity_status="NOT_VERIFIED", publish_status="NOT_VERIFIED",
                          verification_source=source, source_comparison=None)
            result["checks"] = [*directory_result["checks"], {
                "check": "verification_source", "status": "NOT_VERIFIED", "detector_class": "HOST_UNAVAILABLE",
                "detail": "Không tìm thấy story.zip trong thư mục nội dung.",
            }]
            return result
    else:
        uploaded = state.get(VERIFICATION_UPLOAD_BYTES_KEY)
        if not isinstance(uploaded, bytes) or not uploaded:
            result = dict(directory_result)
            result.update(status="NOT_VERIFIED", integrity_status="NOT_VERIFIED", publish_status="NOT_VERIFIED",
                          verification_source=source, source_comparison=None)
            result["checks"] = [*directory_result["checks"], {
                "check": "verification_source", "status": "NOT_VERIFIED", "detector_class": "HOST_UNAVAILABLE",
                "detail": "Chưa có bytes của ZIP đã tải lên.",
            }]
            return result
        zip_source = uploaded

    members = read_archive(zip_source)
    result = inspect_members(members, archive=True, parent=parent)
    left = directory_result.get("actual_package_digest_sha256")
    right = result.get("actual_package_digest_sha256")
    matches = bool(left and right and left == right)
    comparison = {
        "status": "PASS" if matches else "FAIL",
        "directory_digest_sha256": left,
        "zip_digest_sha256": right,
        "detail": "ZIP khớp dữ liệu thư mục." if matches else "ZIP và thư mục là hai phiên bản khác nhau.",
    }
    result["verification_source"] = source
    result["source_comparison"] = comparison
    result["checks"] = [*result["checks"], {
        "check": "source_match", "status": comparison["status"], "detector_class": "DETERMINISTIC",
        "detail": comparison["detail"],
    }]
    if not matches:
        result.update(status="FAIL", integrity_status="FAIL", publish_status="FAIL")
    return result


def required_report_keys(reports: Mapping[str, Any]) -> set[str]:
    manifest = _object(reports.get("workflow"))
    stage = manifest.get("package_stage")
    validation = _object(reports.get("validation"))
    required = {"story", "validation"}
    if stage not in STAGES or stage in {"STAGE3", "STAGE4"}:
        required.add("quality")
    if stage in STAGES:
        anchor_required = (manifest.get("active_profile") == "SERIAL_DETECTIVE"
                           or any(row.get("path") == "series_anchor.json" for row in _items(manifest.get("files"))))
    else:
        anchor_required = series_required(validation)
    if anchor_required:
        required.add("anchor")
    return required


def review_package(root: Path, reports: Mapping[str, Any], statuses: Mapping[str, str], state: Mapping[str, Any]) -> dict[str, Any]:
    validation = _object(reports.get("validation"))
    quality = _object(reports.get("quality"))
    overrides = state.get("story_overrides", {}) if state.get("story_override_root") == str(root.resolve()) else {}
    workflow = inspect_selected_workflow(
        root, state,
        overridden=any(key in {"story", "validation", "quality", "anchor"} for key in overrides),
    )
    video_plan_result: dict[str, Any] | None = None
    video_plan_issue: str | None = None
    if workflow.get("stage") == "STAGE4":
        video_plan_result = validate_video_prompt_plan(_object(reports.get("video_prompts")), root=root)
        errors = list(video_plan_result.get("errors") or [])
        clips = _items(_object(reports.get("video_prompts")).get("clips"))
        span_errors = sum("source_text_digest/offset" in str(error) for error in errors)
        if errors:
            span_detail = f"{span_errors}/{len(clips)} clip có source digest hoặc offset không khớp story.json; " if span_errors else ""
            video_plan_issue = f"video_prompt_plan: {span_detail}{len(errors)} lỗi canonical; export bị khóa."
            workflow["checks"] = [*workflow["checks"], {
                "check": "video_prompt_plan", "status": "FAIL", "detector_class": "DETERMINISTIC",
                "detail": video_plan_issue.removeprefix("video_prompt_plan: "),
            }]
            workflow.update(status="FAIL", stage_gate_status="FAIL", publish_status="FAIL")
        else:
            workflow["checks"] = [*workflow["checks"], {
                "check": "video_prompt_plan", "status": "PASS", "detector_class": "DETERMINISTIC",
                "detail": f"{len(clips)} clip đạt kiểm tra cấu trúc canonical và source span.",
            }]
    workflow["video_prompt_validation"] = video_plan_result
    bindings = inspect_report_bindings(root, reports, story_bytes=overrides.get("story"))
    assets = inspect_project_assets(root, reports)
    issues = [{"section": "Kiểm định", "text": text} for text in gate_issues(validation)]
    if video_plan_issue:
        issues.append({"section": "Kế hoạch video", "text": video_plan_issue})
    if workflow["stage"] or workflow["status"] == "FAIL":
        issues.extend({"section": "Gói & quy trình", "text": f"{c['check']}: {c['detail']}"}
                      for c in workflow["checks"]
                      if c["status"] not in {"PASS", "WARN"} and c["check"] != "video_prompt_plan")
    if quality and _object(quality.get("summary")).get("publish_verdict") != "PASS":
        issues.append({"section": "Chất lượng", "text": "Báo cáo chất lượng gói chưa kết luận PASS."})
    for key, label in (("story", "Nội dung"), ("validation", "Kiểm định"), ("quality", "Chất lượng"), ("anchor", "Series")):
        if statuses.get(key, "").startswith("Không hợp lệ"):
            issues.append({"section": label, "text": f"{label}: {statuses[key]}"})
    for row in bindings:
        if "đã cũ" in row["status"]:
            issues.append({"section": "Kiểm định" if row["report"] == "validation" else "Chất lượng", "text": f"{row['report']}: {row['status']}"})
    if validation.get("active_profile") == "SERIAL_DETECTIVE" and not reports.get("anchor"):
        issues.append({"section": "Series", "text": "Hồ sơ SERIAL_DETECTIVE cần series_anchor.json."})
    defects = int(_object(validation.get("summary")).get("material_defect_remaining_count") or 0)
    story_ready = bool(reports.get("story")) and gate_summary(validation)["ready"] and defects == 0 and not any(i["section"] in {"Kiểm định", "Nội dung"} for i in issues)
    asset_issues = [row for row in assets if row["issues"]]
    package_ready = (
        story_ready and bool(quality) and _object(quality.get("summary")).get("publish_verdict") == "PASS"
        and not _items(quality.get("blockers")) and not issues and not asset_issues
    )
    locally_verified = workflow["status"] == "PASS" and not overrides
    package_ready = bool(package_ready and locally_verified)
    return {"workflow": workflow, "locally_verified": locally_verified, "story_ready": story_ready, "package_ready": package_ready, "issues": issues,
            "assets": assets, "asset_issues": asset_issues, "bindings": bindings}
