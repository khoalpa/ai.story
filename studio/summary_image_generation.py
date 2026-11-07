"""Pilot-first image generation orchestration for Summary packages."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from studio.artifact_validation import strict_json_bytes
from studio.summary_audit import audit_summary_package, load_summary_members
from studio.summary_image_provider import ImageGenerationRequest, SummaryImageProvider
from studio.summary_media import REVIEW_CHECKS, build_render_plan, default_render_config
from studio.summary_schema import validate_summary_document
from studio.summary_visual_schema import validate_summary_visual_plan

HIGH_RISK_VISUAL_TYPES = {"DATA_CHART", "DIAGRAM", "RECONSTRUCTION", "QUOTE_CARD"}


@dataclass(frozen=True)
class RenderRunResult:
    status: str
    output_root: Path
    render_plan_path: Path
    render_log_path: Path
    media_review_path: Path
    generated: int
    failed: int


def render_summary_package(
    source_package: Path,
    output_root: Path,
    provider: SummaryImageProvider,
    *,
    orientation: str,
    max_attempts: int = 3,
    pilot_count: int = 2,
    overwrite: bool = False,
) -> RenderRunResult:
    """Generate one orientation from an audited Summary stage package.

    Semantic review intentionally remains NOT_CHECKED. The generated review draft
    must be completed after real images are observed before Stage 2/3 can become
    COMPLETE.
    """
    if orientation not in {"landscape", "portrait"}:
        raise ValueError("orientation phải là landscape hoặc portrait")
    if not 1 <= max_attempts <= 10:
        raise ValueError("max_attempts phải từ 1 đến 10")
    if not 1 <= pilot_count <= 10:
        raise ValueError("pilot_count phải từ 1 đến 10")
    audit = audit_summary_package(source_package)
    if audit.status != "PASS":
        raise ValueError("Summary package nguồn không đạt audit: " + "; ".join(audit.errors))
    members = load_summary_members(source_package)
    summary = strict_json_bytes(members.get("summary.json", b""))
    visual = strict_json_bytes(members.get("summary_visual_plan.json", b""))
    errors = validate_summary_document(summary) + validate_summary_visual_plan(visual, summary)
    if errors:
        raise ValueError("Summary source không hợp lệ: " + "; ".join(errors))

    config = default_render_config()
    config["required_orientations"] = [orientation]
    config["optional_orientations"] = []
    config["max_attempts_per_asset"] = max_attempts
    plan = build_render_plan(summary, visual, config)
    scene_by_id = {scene["scene_id"]: scene for scene in visual["scenes"]}
    ordered_assets = sorted(
        plan["assets"],
        key=lambda asset: (
            scene_by_id[asset["scene_id"]]["visual_type"] not in HIGH_RISK_VISUAL_TYPES,
            asset["scene_id"],
        ),
    )
    pilot_ids = {asset["asset_id"] for asset in ordered_assets[:pilot_count]}
    output_root.mkdir(parents=True, exist_ok=True)
    if orientation == "portrait":
        _materialize_inherited_landscape(members, output_root)
    orientation_root = output_root / orientation
    orientation_root.mkdir(parents=True, exist_ok=True)
    log_rows: list[dict[str, Any]] = []
    generated = failed = 0
    pilot_failed = False

    for asset in ordered_assets:
        scene = scene_by_id[asset["scene_id"]]
        destination = output_root / Path(asset["output_path"])
        is_pilot = asset["asset_id"] in pilot_ids
        if pilot_failed and not is_pilot:
            asset["status"] = "FAILED"
            failed += 1
            log_rows.append(
                _log_row(
                    asset,
                    None,
                    None,
                    None,
                    ["PILOT_GATE_FAILED"],
                    provider.name,
                    error="Không mở rộng batch vì pilot chưa đạt kỹ thuật",
                    reused=False,
                )
            )
            continue
        if destination.exists() and not overwrite:
            raw = destination.read_bytes()
            existing_issues, width, height = _technical_issues(raw, orientation)
            if not existing_issues:
                asset["status"] = "GENERATED"
                log_rows.append(_log_row(asset, raw, width, height, [], provider.name, reused=True))
                generated += 1
                continue
            raise ValueError(f"Tệp đã tồn tại nhưng không hợp lệ: {destination}")

        references = _reference_paths(
            output_root, asset["scene_id"], orientation
        )
        issues: list[str] = ["TOOL_FAILURE"]
        raw = b""
        width = height = None
        last_error: str | None = None
        asset_provider = provider.name
        for attempt in range(1, max_attempts + 1):
            asset["status"] = "GENERATING"
            asset["attempt_count"] = attempt
            request = ImageGenerationRequest(
                asset_id=asset["asset_id"],
                scene_id=asset["scene_id"],
                orientation=orientation,
                prompt=str(scene[f"{orientation}_prompt"]),
                output_path=asset["output_path"],
                reference_paths=references,
                metadata={
                    "visual_type": scene["visual_type"],
                    "visual_fact": scene["visual_fact"],
                    "style_lock": visual["style_lock"],
                    "pilot": asset["asset_id"] in pilot_ids,
                    "source_locator_ids": scene["source_locator_ids"],
                    "numeric_fact_ids": scene["numeric_fact_ids"],
                },
            )
            try:
                if scene["visual_type"] == "DATA_CHART":
                    raw = _render_data_chart(summary, scene, orientation)
                    asset_provider = "deterministic-chart"
                else:
                    result = provider.generate(request)
                    raw = result.data
                issues, width, height = _technical_issues(raw, orientation)
                last_error = None if not issues else ", ".join(issues)
            except (OSError, RuntimeError, ValueError) as exc:
                issues, last_error = ["TOOL_FAILURE"], str(exc)
            if not issues:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                asset["status"] = "GENERATED"
                generated += 1
                break
            asset["status"] = "RETRY_PENDING" if attempt < max_attempts else "FAILED"
        if issues:
            failed += 1
            if is_pilot:
                pilot_failed = True
        log_rows.append(
            _log_row(
                asset, raw or None, width, height, issues, asset_provider,
                error=last_error, reused=False,
            )
        )

    review_assets = []
    for asset in plan["assets"]:
        row = next(item for item in log_rows if item["asset_id"] == asset["asset_id"])
        has_file = row["status"] == "GENERATED"
        review_assets.append(
            {
                "asset_id": asset["asset_id"],
                "checks": {
                    check: "NOT_CHECKED" if has_file else "NOT_APPLICABLE"
                    for check in REVIEW_CHECKS
                },
            }
        )
    render_log = {
        "schema_version": "1.0.0",
        "prompt_version": "1.5.0",
        "provider": provider.name,
        "orientation": orientation,
        "assets": log_rows,
    }
    review = {"schema_version": "1.0.0", "assets": review_assets}
    render_plan_path = output_root / "summary_render_plan.json"
    render_log_path = output_root / "summary_render_log.json"
    media_review_path = output_root / "summary_media_review_draft.json"
    _write_json(render_plan_path, plan)
    _write_json(render_log_path, render_log)
    _write_json(media_review_path, review)
    return RenderRunResult(
        "COMPLETE" if failed == 0 else "PARTIAL",
        output_root,
        render_plan_path,
        render_log_path,
        media_review_path,
        generated,
        failed,
    )


def _reference_paths(root: Path, scene_id: str, orientation: str) -> tuple[Path, ...]:
    if orientation != "portrait":
        return ()
    landscape = root / "landscape" / f"{scene_id}.png"
    return (landscape,) if landscape.is_file() else ()


def _materialize_inherited_landscape(
    members: Mapping[str, bytes], output_root: Path
) -> None:
    for name, raw in members.items():
        if not name.startswith("landscape/"):
            continue
        relative = Path(name)
        if len(relative.parts) != 2 or relative.suffix.casefold() != ".png":
            continue
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != raw:
                raise ValueError(
                    f"Landscape hiện có khác bytes package nguồn: {destination}"
                )
        else:
            destination.write_bytes(raw)


def _render_data_chart(
    summary: Mapping[str, Any], scene: Mapping[str, Any], orientation: str
) -> bytes:
    facts = {
        row["numeric_fact_id"]: row
        for row in summary["numeric_facts"]
        if isinstance(row, Mapping)
    }
    selected = [facts[item] for item in scene["numeric_fact_ids"] if item in facts]
    if not selected:
        raise ValueError("DATA_CHART thiếu numeric facts canonical")
    size = (1600, 900) if orientation == "landscape" else (900, 1600)
    image = Image.new("RGB", size, "#f7f3e8")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    margin = 100
    chart_width = size[0] - margin * 2
    chart_height = size[1] - margin * 2
    values = [float(row["value"]) for row in selected]
    maximum = max((abs(value) for value in values), default=1.0) or 1.0
    slot = chart_width / len(selected)
    for index, (row, value) in enumerate(zip(selected, values)):
        bar_width = max(8, int(slot * 0.55))
        left = int(margin + index * slot + (slot - bar_width) / 2)
        bottom = margin + chart_height
        height = max(2, int(chart_height * 0.72 * abs(value) / maximum))
        top = bottom - height
        draw.rounded_rectangle(
            (left, top, left + bar_width, bottom), radius=12, fill="#356a77"
        )
        label = format(row["value"], "g")
        draw.text((left, max(margin, top - 48)), label, fill="#17242a", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _technical_issues(raw: bytes, orientation: str) -> tuple[list[str], int | None, int | None]:
    if not raw:
        return ["EMPTY_FILE"], None, None
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError):
        return ["CORRUPT_IMAGE"], None, None
    issues = []
    if orientation == "landscape" and width <= height:
        issues.append("WRONG_ORIENTATION")
    if orientation == "portrait" and height <= width:
        issues.append("WRONG_ORIENTATION")
    return issues, width, height


def _log_row(
    asset: Mapping[str, Any],
    raw: bytes | None,
    width: int | None,
    height: int | None,
    issues: Sequence[str],
    provider: str,
    *,
    error: str | None = None,
    reused: bool,
) -> dict[str, Any]:
    return {
        "asset_id": asset["asset_id"],
        "path": asset["output_path"],
        "status": "GENERATED" if raw is not None and not issues else "FAILED",
        "attempt_count": asset["attempt_count"],
        "size_bytes": len(raw) if raw is not None else None,
        "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
        "width": width,
        "height": height,
        "issues": list(issues),
        "provider": provider,
        "reused": reused,
        "error": error,
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = ["RenderRunResult", "render_summary_package"]
