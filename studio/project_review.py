"""Shared package assessment for both Studio summaries."""
from pathlib import Path
from typing import Any, Mapping

from studio.package_quality_report import _items, _object
from studio.project_assets import inspect_project_assets, inspect_report_bindings
from studio.report_semantics import gate_issues, gate_summary


def review_package(root: Path, reports: Mapping[str, Any], statuses: Mapping[str, str], state: Mapping[str, Any]) -> dict[str, Any]:
    validation = _object(reports.get("validation"))
    quality = _object(reports.get("quality"))
    overrides = state.get("story_overrides", {}) if state.get("story_override_root") == str(root.resolve()) else {}
    bindings = inspect_report_bindings(root, reports, story_bytes=overrides.get("story"))
    assets = inspect_project_assets(root, reports)
    issues = [{"section": "Kiểm định", "text": text} for text in gate_issues(validation)]
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
    locally_verified = len(bindings) == 2 and all(row["status"] == "Khớp kịch bản" for row in bindings) and all(row["hash_verified"] and not row["issues"] for row in assets)
    return {"locally_verified": locally_verified, "story_ready": story_ready, "package_ready": package_ready, "issues": issues,
            "assets": assets, "asset_issues": asset_issues, "bindings": bindings}
