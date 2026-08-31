"""Fail-closed Stage 4 source admission for CURRENT workflow packages."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from studio.prompt_contract import PromptContract, load_prompt_contract
from studio.workflow_package import inspect_members, read_archive, read_json


def validate_stage4_source(source: Path | bytes, operation: str, *,
                           contract: PromptContract | None = None) -> dict[str, Any]:
    contract = contract or load_prompt_contract()
    errors: list[str] = []
    try:
        members = read_archive(source)
        inspection = inspect_members(members, archive=True, contract=contract)
    except (OSError, ValueError) as exc:
        return {"status": "FAIL", "errors": [str(exc)], "members": {}, "inspection": {}}
    stages = contract.workflow_package_stages
    expected_stage = stages[2] if operation == "CREATE" else stages[3] if operation == "REPAIR" else None
    if expected_stage is None:
        errors.append("Stage 4 chỉ hỗ trợ operation CREATE hoặc REPAIR.")
    if inspection.get("compatibility") != "NATIVE_CURRENT" or inspection.get("stage") != expected_stage:
        errors.append(f"{operation} yêu cầu exact {expected_stage or 'CURRENT'} story.zip.")
    if inspection.get("integrity_status") != "PASS":
        errors.append("Gói nguồn chưa vượt toàn bộ kiểm tra integrity CURRENT.")
    try:
        quality = read_json(members["package_quality_report.json"])
        summary = quality.get("summary")
        if not isinstance(summary, Mapping) or summary.get("publish_verdict") != "PASS":
            errors.append("package_quality_report.publish_verdict không PASS.")
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        errors.append(f"Package-quality report không hợp lệ: {exc}")
    if operation == "CREATE" and contract.video_prompt_file_name in members:
        errors.append("Stage 3 nguồn CREATE không được chứa video_prompts canonical.")
    return {"status": "FAIL" if errors else "PASS", "errors": errors,
            "members": members, "inspection": inspection}


__all__ = ["validate_stage4_source"]
