"""Shared interpretation of report claims (not an independent story verifier)."""
from __future__ import annotations

import math
from typing import Any, Mapping

from studio.package_quality_report import _items, _object


def display_score(value: Any, maximum: int = 10) -> str:
    """Accept legacy 0–10 and exported 0–100 scores; never invent missing scores."""
    if isinstance(value, bool):
        return "—"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(score) or score < 0 or score > 100:
        return "—"
    if maximum == 10 and score > 10:
        score /= 10
    return f"{score:.1f}/{maximum}"


def gate_is_not_applicable(gate: Mapping[str, Any], report: Mapping[str, Any]) -> bool:
    """Only continuity can be waived here, with explicit standalone evidence."""
    return (
        gate.get("status") == "NOT_APPLICABLE"
        and gate.get("gate_id") in {"CONTINUITY", "CONTINUITY_PORTABILITY"}
        and report.get("active_profile") in {"ADULT_STANDARD", "YOUTH_SAFE"}
        and str(_object(gate.get("metrics")).get("applicability_reason") or "").strip().casefold()
        in {"standalone story", "standalone"}
    )


def gate_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    raw = report.get("gates")
    gates = _items(raw)
    passed = sum(g.get("status") == "PASS" for g in gates)
    skipped = sum(gate_is_not_applicable(g, report) for g in gates)
    unresolved = [g for g in gates if g.get("status") != "PASS" and not gate_is_not_applicable(g, report)]
    malformed = not isinstance(raw, list) or len(gates) != len(raw)
    return {
        "passed": passed, "skipped": skipped, "unresolved": unresolved,
        "ready": bool(gates) and passed > 0 and not unresolved and not malformed,
        "label": f"{passed} đạt · {skipped} không áp dụng",
    }


def series_required(validation: Mapping[str, Any]) -> bool:
    return not any(gate_is_not_applicable(g, validation) for g in _items(validation.get("gates")))


def gate_issues(validation: Mapping[str, Any]) -> list[str]:
    summary = gate_summary(validation)
    issues = [
        f"{g.get('gate_id', 'Cổng không rõ')}: {g.get('status', 'Chưa xác minh')}"
        + (f" · {g['failure_reason']}" if g.get("failure_reason") else "")
        for g in summary["unresolved"]
    ]
    if validation and not summary["ready"] and not issues:
        issues.append("Danh sách cổng kiểm định trống hoặc không hợp lệ.")
    return issues
