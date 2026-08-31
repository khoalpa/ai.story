"""Shared package assessment for both Studio summaries."""
from pathlib import Path
from typing import Any, Mapping

from studio.package_quality_report import _items, _object
from studio.project_assets import inspect_project_assets, inspect_report_bindings
from studio.report_semantics import gate_issues, gate_summary, series_required
from studio.workflow_package import STAGES, inspect_directory


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
    workflow = inspect_directory(root, overridden=any(key in {"story", "validation", "quality", "anchor"} for key in overrides))
    bindings = inspect_report_bindings(root, reports, story_bytes=overrides.get("story"))
    assets = inspect_project_assets(root, reports)
    issues = [{"section": "Kiểm định", "text": text} for text in gate_issues(validation)]
    if workflow["stage"] or workflow["status"] == "FAIL":
        issues.extend({"section": "Gói & quy trình", "text": f"{c['check']}: {c['detail']}"}
                      for c in workflow["checks"] if c["status"] != "PASS")
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
