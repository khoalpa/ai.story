"""Deterministic prompt-conformance checks for story artifacts and archives."""
from __future__ import annotations

import hashlib
import json
import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from PIL import Image, UnidentifiedImageError

from studio.prompt_contract import PromptContract, load_prompt_contract


@dataclass
class ValidationResult:
    artifact: str
    status: str = "PASS"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)
    prompt_version: str = ""
    prompt_sha256: str = ""
    compatibility_mode: str = "NATIVE_CURRENT"

    def fail(self, message: str) -> None:
        self.status = "FAIL"
        self.errors.append(message)

    def unverified(self, message: str) -> None:
        if self.status == "PASS":
            self.status = "NOT_VERIFIED"
        self.warnings.append(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact, "status": self.status,
            "prompt_version": self.prompt_version, "prompt_sha256": self.prompt_sha256,
            "compatibility_mode": self.compatibility_mode, "checks": self.checks,
            "errors": self.errors, "warnings": self.warnings,
        }


def _result(artifact: str, contract: PromptContract) -> ValidationResult:
    return ValidationResult(
        artifact=artifact, prompt_version=contract.version_label, prompt_sha256=contract.sha256
    )


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def strict_json_bytes(raw: bytes) -> Mapping[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("JSON có UTF-8 BOM")
    text = raw.decode("utf-8", errors="strict")

    def reject_constant(value: str) -> None:
        raise ValueError(f"JSON constant không hữu hạn: {value}")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"JSON number không hữu hạn: {value}")
        return number

    value = json.loads(
        text, object_pairs_hook=_pairs_no_duplicates,
        parse_constant=reject_constant, parse_float=finite_float,
    )
    if not isinstance(value, dict):
        raise ValueError("JSON root phải là object")
    return value


def _validate_json_file(
    path: Path, *, required: tuple[str, ...], exact_order: tuple[str, ...] | None,
    contract: PromptContract, schema_version: str | None = None,
) -> tuple[ValidationResult, Mapping[str, Any] | None]:
    result = _result(path.name, contract)
    try:
        document = strict_json_bytes(path.read_bytes())
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result.fail(f"JSON không hợp lệ: {exc}")
        return result, None
    missing = [key for key in required if key not in document]
    if missing:
        result.fail("Thiếu field: " + ", ".join(missing))
    if exact_order is not None and tuple(document) != exact_order:
        result.fail("Root field/order không đúng contract: " + ", ".join(document))
    if schema_version is not None and document.get("schema_version") != schema_version:
        result.fail(
            f"schema_version={document.get('schema_version')!r}; yêu cầu {schema_version!r}"
        )
    result.checks["strict_json"] = "PASS" if not result.errors else "FAIL"
    return result, document


def validate_story(path: Path, contract: PromptContract | None = None) -> ValidationResult:
    contract = contract or load_prompt_contract()
    result, document = _validate_json_file(
        path, required=("schema_version", "meta", "characters", "outline", "script"),
        exact_order=("schema_version", "meta", "characters", "outline", "script"), contract=contract,
    )
    if document is None:
        return result
    meta = document.get("meta")
    if not isinstance(meta, dict):
        result.fail("meta phải là object")
    else:
        commitment = meta.get("story_quality_commitment")
        if not isinstance(commitment, dict):
            result.fail("Thiếu meta.story_quality_commitment hiện hành")
        elif commitment.get("schema_version") != contract.story_quality_commitment_schema_version:
            result.fail("story_quality_commitment.schema_version không khớp prompt")
    if not isinstance(document.get("characters"), list) or not isinstance(document.get("script"), list):
        result.fail("characters và script phải là array")
    result.checks["story_contract"] = "PASS" if not result.errors else "FAIL"
    return result


def validate_story_validation(
    path: Path, story_path: Path | None = None, contract: PromptContract | None = None
) -> ValidationResult:
    contract = contract or load_prompt_contract()
    root = (
        "schema_version", "prompt_version", "story_sha256",
        "story_quality_commitment_digest_sha256", "active_profile", "summary",
        "scene_zone_map", "dialogue_audio", "quality", "engagement", "gates",
        "refinement", "evidence_graph",
    )
    result, document = _validate_json_file(
        path, required=root, exact_order=root, contract=contract,
        schema_version=contract.story_validation_schema_version,
    )
    if document is not None and story_path is not None and story_path.is_file():
        digest = hashlib.sha256(story_path.read_bytes()).hexdigest()
        if document.get("story_sha256") != digest:
            result.fail("story_sha256 không khớp exact bytes của story.json")
        result.checks["story_sha256_binding"] = "PASS" if document.get("story_sha256") == digest else "FAIL"
    return result


def validate_series_anchor(path: Path, contract: PromptContract | None = None) -> ValidationResult:
    contract = contract or load_prompt_contract()
    root = ("schema_version", "series", "canon", "continuity", "episode_ledger", "canon_change_log")
    result, _document = _validate_json_file(
        path, required=root, exact_order=root, contract=contract,
        schema_version=contract.series_anchor_schema_version,
    )
    return result


def validate_package_quality(path: Path, contract: PromptContract | None = None) -> ValidationResult:
    contract = contract or load_prompt_contract()
    root = (
        "schema_version", "report_id", "generated_at_utc", "package_identity",
        "registry_bindings", "summary", "dimensions", "measurement_ledger",
        "story_evidence", "image_evidence", "blockers", "recommendations", "validation",
    )
    result, document = _validate_json_file(
        path, required=root, exact_order=root, contract=contract,
        schema_version=contract.package_quality_schema_version,
    )
    if document is not None:
        validation = document.get("validation")
        if not isinstance(validation, dict) or validation.get("status") != "PASS":
            result.fail("package quality validation.status phải là PASS")
        image_evidence = document.get("image_evidence")
        asset_results = image_evidence.get("asset_results") if isinstance(image_evidence, dict) else None
        if not isinstance(asset_results, list) or len(asset_results) != 20:
            result.fail("image_evidence.asset_results phải bind đúng 20 ảnh")
    return result


def _safe_archive_names(
    infos: Iterable[zipfile.ZipInfo], result: ValidationResult,
) -> dict[str, zipfile.ZipInfo]:
    names: dict[str, zipfile.ZipInfo] = {}
    normalized: set[str] = set()
    for info in infos:
        path = PurePosixPath(info.filename.replace("\\", "/"))
        name = path.as_posix()
        if info.is_dir():
            continue
        if path.is_absolute() or ".." in path.parts or not path.parts:
            result.fail(f"Đường dẫn ZIP không an toàn: {info.filename}")
            continue
        folded = name.casefold()
        if folded in normalized:
            result.fail(f"Đường dẫn ZIP trùng sau chuẩn hóa: {name}")
            continue
        normalized.add(folded)
        names[name] = info
    return names


def _validate_png(raw: bytes, name: str, expected_size: tuple[int, int], result: ValidationResult) -> None:
    from io import BytesIO

    try:
        with Image.open(BytesIO(raw)) as image:
            image.load()
            if image.format != "PNG":
                result.fail(f"{name}: định dạng {image.format}, yêu cầu PNG")
            if image.size != expected_size:
                result.fail(f"{name}: kích thước {image.size}, yêu cầu {expected_size}")
    except (OSError, UnidentifiedImageError) as exc:
        result.fail(f"{name}: ảnh không hợp lệ: {exc}")


def validate_archive(path: Path, contract: PromptContract | None = None) -> ValidationResult:
    contract = contract or load_prompt_contract()
    # CURRENT packages are identified structurally, not merely by filename.
    # Import locally because workflow_package reuses strict_json_bytes above.
    from studio.workflow_package import inspect_members, read_archive

    try:
        with zipfile.ZipFile(path) as probe:
            is_current = "workflow_manifest.json" in probe.namelist()
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        result = _result(path.name, contract)
        result.fail(f"ZIP không hợp lệ: {exc}")
        return result
    if is_current:
        try:
            members = read_archive(path)
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
            result = _result(path.name, contract)
            result.fail(f"ZIP không hợp lệ: {exc}")
            return result
        inspection = inspect_members(members, archive=True, contract=contract)
        result = _result(path.name, contract)
        result.status = inspection["status"]
        result.compatibility_mode = inspection["compatibility"]
        for item in inspection["checks"]:
            result.checks[item["check"]] = item["status"]
            if item["status"] == "FAIL":
                result.errors.append(f'{item["check"]}: {item["detail"]}')
            elif item["status"] == "NOT_VERIFIED":
                result.warnings.append(f'{item["check"]}: {item["detail"]}')
        return result

    result = _result(path.name, contract)
    checkpoint = path.name.casefold() == "stage2_checkpoint.zip"
    result.compatibility_mode = "MIGRATION_REQUIRED"
    landscape = tuple(f"landscape/{name}" for name in contract.image_basenames)
    portrait = tuple(f"portrait/{name}" for name in contract.image_basenames)
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                result.fail(f"CRC lỗi: {bad}")
            names = _safe_archive_names(archive.infolist(), result)
            anchor_present = "series_anchor.json" in names
            expected = (
                {"story.json", "visual_bible.json", *landscape}
                if checkpoint else
                {"story.json", "story_validation.json", "package_quality_report.json", *landscape, *portrait}
                | ({"series_anchor.json"} if anchor_present else set())
            )
            actual = set(names)
            for missing in sorted(expected - actual):
                result.fail(f"Thiếu file: {missing}")
            for extra in sorted(actual - expected):
                result.fail(f"File thừa: {extra}")
            json_valid = True
            for name, info in names.items():
                if PurePosixPath(name).suffix.casefold() == ".json":
                    try:
                        strict_json_bytes(archive.read(info))
                    except (UnicodeError, ValueError) as exc:
                        json_valid = False
                        result.fail(f"{name}: JSON không hợp lệ: {exc}")
            result.checks["archive_json"] = "PASS" if json_valid else "FAIL"
            for name in landscape:
                if name in actual:
                    _validate_png(archive.read(names[name]), name, contract.landscape_size, result)
            if not checkpoint:
                for name in portrait:
                    if name in actual:
                        _validate_png(archive.read(names[name]), name, contract.portrait_size, result)
            result.checks["archive_file_set"] = "PASS" if actual == expected else "FAIL"
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        result.fail(f"ZIP không hợp lệ: {exc}")
    if not result.errors:
        result.unverified(
            "Gói không có workflow_manifest.json nên chỉ được đọc như LEGACY_INPUT_COMPATIBILITY; "
            "cần migrate sang story.zip CURRENT trước khi có thể xác nhận workflow."
        )
    return result


def validate_project(path: Path, contract: PromptContract | None = None) -> list[ValidationResult]:
    contract = contract or load_prompt_contract()
    if path.is_file() and path.suffix.casefold() == ".zip":
        return [validate_archive(path, contract)]
    if not path.is_dir():
        result = _result(str(path), contract)
        result.fail("Đường dẫn không phải thư mục hoặc ZIP")
        return [result]
    results: list[ValidationResult] = []
    story = path / "story.json"
    if story.is_file():
        results.append(validate_story(story, contract))
    validation = path / "story_validation.json"
    if validation.is_file():
        results.append(validate_story_validation(validation, story if story.is_file() else None, contract))
    anchor = path / "series_anchor.json"
    if anchor.is_file():
        results.append(validate_series_anchor(anchor, contract))
    quality = path / "package_quality_report.json"
    if quality.is_file():
        results.append(validate_package_quality(quality, contract))
    for archive_name in ("stage1_checkpoint.zip", "stage2_checkpoint.zip", "story.zip"):
        archive = path / archive_name
        if archive.is_file():
            results.append(validate_archive(archive, contract))
    if not results:
        result = _result(str(path), contract)
        result.fail("Không tìm thấy artifact chuẩn để kiểm tra")
        results.append(result)
    return results


__all__ = [
    "ValidationResult", "strict_json_bytes", "validate_archive", "validate_project",
    "validate_package_quality", "validate_series_anchor", "validate_story",
    "validate_story_validation",
]
