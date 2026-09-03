from __future__ import annotations

import io
import json

import pytest

from studio.package_quality_report import (
    _format_generated_at,
    _read_report,
    _short_digest,
    package_quality_summary,
)


def test_read_report_accepts_utf8_json_object() -> None:
    source = io.BytesIO(json.dumps({"schema_version": "2.0"}).encode("utf-8"))
    assert _read_report(source) == {"schema_version": "2.0"}


def test_read_report_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        _read_report(io.BytesIO(b"[]"))


def test_short_digest_preserves_context_at_both_ends() -> None:
    digest = "0123456789abcdef0123456789abcdef"
    assert _short_digest(digest) == "01234567…9abcdef"


def test_generated_time_is_human_readable() -> None:
    assert _format_generated_at("2026-08-26T12:04:12Z") != "2026-08-26T12:04:12Z"


def test_current_quality_schema_is_normalized() -> None:
    report = {
        "summary": {"global_score": 94, "coverage_ratio": 1, "publish_verdict": "PASS"},
        "dimensions": [
            {"dimension_id": "STORY_CONTENT", "status": "PASS", "applicability": "APPLICABLE"},
            {"dimension_id": "SAFETY", "status": "PASS", "applicability": "APPLICABLE"},
        ],
        "image_evidence": {"asset_results": [{
            "path": "portrait/cover.png", "validation_status": "PASS",
            "provenance_status": "PASS", "visual_quality_status": "ASSESSED_PASS",
        }]},
    }

    summary = package_quality_summary(report)
    assert summary["score"] == 94
    assert summary["coverage"] == 1
    assert summary["gates_passed"] == len(summary["gates"]) == 2
    assert summary["assets_passed"] == len(summary["assets"]) == 1
