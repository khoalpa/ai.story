"""Deterministic prompt-conformance checks for story artifacts and archives."""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from PIL import Image, UnidentifiedImageError

from studio.prompt_contract import PromptContract, load_prompt_contract

STORY_VALIDATION_FIELDS = (
    "schema_version", "prompt_version", "stage", "status", "input_sources",
    "checks", "limitations", "remaining_work", "archive_validation",
)


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
        exact_order=None, contract=contract, schema_version="4.1.3",
    )
    if document is None:
        return result
    meta = document.get("meta")
    if not isinstance(meta, dict):
        result.fail("meta phải là object")
    elif set(meta) != {"title", "series", "episode", "author", "channel", "profile", "age_band", "language", "genre", "tone", "target_minutes", "estimated_minutes", "timing_method", "tags"}:
        result.fail("meta không đúng closed schema 4.1.3")
    if not isinstance(document.get("characters"), list) or not isinstance(document.get("script"), list):
        result.fail("characters và script phải là array")
    result.checks["story_contract"] = "PASS" if not result.errors else "FAIL"
    return result


def validate_story_validation(
    path: Path, story_path: Path | None = None, contract: PromptContract | None = None
) -> ValidationResult:
    contract = contract or load_prompt_contract()
    root = STORY_VALIDATION_FIELDS
    result, document = _validate_json_file(
        path, required=root, exact_order=root, contract=contract,
        schema_version="4.1.3",
    )
    if document is not None:
        if document.get("prompt_version") != "4.1.6":
            result.fail("prompt_version phải là 4.1.6")
        if type(document.get("stage")) is not int or document["stage"] not in range(1, 5):
            result.fail("stage phải là integer 1..4")
        if document.get("status") not in {"COMPLETE", "PARTIAL", "BLOCKED"}:
            result.fail("status không hợp lệ")
    return result


def validate_story_validation_bytes(
    raw: bytes, story_raw: bytes, *, character_root: Path | None = None,
    contract: PromptContract | None = None,
) -> ValidationResult:
    """Validate a candidate report without publishing it to the workspace."""
    contract = contract or load_prompt_contract()
    result = _result("validation_report.json", contract)
    try:
        report = strict_json_bytes(raw)
        story = strict_json_bytes(story_raw)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result.fail(f"JSON không hợp lệ: {exc}")
        return result

    missing = [key for key in STORY_VALIDATION_FIELDS if key not in report]
    if missing:
        result.fail("Thiếu field: " + ", ".join(missing))
    if tuple(report) != STORY_VALIDATION_FIELDS:
        result.fail("Root field/order không đúng contract: " + ", ".join(report))
    if report.get("schema_version") != contract.story_validation_schema_version:
        result.fail(
            f"schema_version={report.get('schema_version')!r}; "
            f"yêu cầu {contract.story_validation_schema_version!r}"
        )
    if report.get("active_profile") not in {
        "YOUTH_SAFE", "ADULT_STANDARD", "SERIAL_DETECTIVE",
    }:
        result.fail(f"active_profile không hợp lệ: {report.get('active_profile')!r}")

    story_digest = hashlib.sha256(story_raw).hexdigest()
    if report.get("story_sha256") != story_digest:
        result.fail("story_sha256 không khớp exact bytes của story.json")

    def canonical_digest(value: Any) -> str:
        text = unicodedata.normalize(
            "NFC", json.dumps(
                value, ensure_ascii=False, separators=(",", ":"),
                allow_nan=False, sort_keys=True,
            )
        )
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    characters = story.get("characters")
    if isinstance(characters, list) and all(isinstance(item, dict) for item in characters):
        projected_characters = [
            {key: value for key, value in item.items() if key != "reference_asset"}
            for item in characters
        ]
        projection = {
            "schema_version": story.get("schema_version"), "meta": story.get("meta"),
            "characters": projected_characters, "outline": story.get("outline"),
            "script": story.get("script"),
        }
        if report.get("story_content_digest_sha256") != canonical_digest(projection):
            result.fail("story_content_digest_sha256 không khớp projection của story.json")

        reference_rows = []
        for character in characters:
            reference = character.get("reference_asset")
            if not isinstance(reference, dict):
                result.fail(f"Thiếu reference_asset của character {character.get('character_id')!r}")
                continue
            path_value = reference.get("reference_image")
            digest_value = reference.get("file_sha256")
            reference_rows.append([character.get("character_id"), path_value, digest_value])
            if character_root is not None:
                if not isinstance(path_value, str):
                    result.fail("reference_image không hợp lệ")
                    continue
                image_path = (character_root / Path(path_value)).resolve()
                if not image_path.is_relative_to(character_root.resolve()) or not image_path.is_file():
                    result.fail(f"Không tìm thấy ảnh nhân vật hợp lệ: {path_value}")
                elif hashlib.sha256(image_path.read_bytes()).hexdigest() != digest_value:
                    result.fail(f"file_sha256 ảnh nhân vật không khớp: {path_value}")
        if report.get("character_reference_set_digest_sha256") != canonical_digest(reference_rows):
            result.fail("character_reference_set_digest_sha256 không khớp story/ảnh nhân vật")
    else:
        result.fail("story.characters phải là array object")

    meta = story.get("meta")
    commitment = meta.get("story_quality_commitment") if isinstance(meta, dict) else None
    expected_commitment = commitment.get("commitment_digest_sha256") if isinstance(commitment, dict) else None
    if not expected_commitment or report.get("story_quality_commitment_digest_sha256") != expected_commitment:
        result.fail("story_quality_commitment_digest_sha256 không khớp story.json")

    result.checks["candidate_binding"] = "PASS" if not result.errors else "FAIL"
    return result


def validate_series_anchor(path: Path, contract: PromptContract | None = None) -> ValidationResult:
    contract = contract or load_prompt_contract()
    root = ("schema_version", "series", "canon", "continuity", "episode_ledger", "canon_change_log")
    result, _document = _validate_json_file(
        path, required=root, exact_order=root, contract=contract,
        schema_version=contract.series_anchor_schema_version,
    )
    return result


def validate_package_quality(
    path: Path, contract: PromptContract | None = None, *, story_path: Path | None = None,
    visual_plan_path: Path | None = None,
) -> ValidationResult:
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
        image_fields = (
            "asset_results", "set_results", "pair_results", "cover_results",
            "evidence_digest_sha256",
        )
        if not isinstance(image_evidence, dict) or tuple(image_evidence) != image_fields:
            result.fail("image_evidence phải là object đúng field/order schema 2.0")
            asset_results = None
        else:
            asset_results = image_evidence.get("asset_results")
        # Prompt 3.15 derives the active image set from visual_plan.json.  Do
        # not validate a SCENE package against the static ZONE fallback.
        active_basenames = contract.image_basenames
        if visual_plan_path is not None and visual_plan_path.is_file():
            try:
                # Local import prevents the workflow module's strict-JSON
                # dependency from forming an import cycle at module load time.
                from studio.workflow_package import active_image_basenames

                visual_plan = strict_json_bytes(visual_plan_path.read_bytes())
                if not isinstance(visual_plan, dict):
                    raise ValueError("visual_plan root phải là object")
                active_basenames = active_image_basenames(visual_plan, contract)
            except (OSError, UnicodeError, ValueError) as exc:
                result.fail(f"Không thể resolve active image set từ visual_plan.json: {exc}")
        expected_paths = {
            *(f"landscape/{name}" for name in active_basenames),
            *(f"portrait/{name}" for name in active_basenames),
        }
        if story_path is not None and story_path.is_file():
            try:
                story = strict_json_bytes(story_path.read_bytes())
                characters = story.get("characters")
                if not isinstance(characters, list):
                    raise ValueError("story.characters phải là array")
                for character in characters:
                    reference = character.get("reference_asset") if isinstance(character, dict) else None
                    name = reference.get("reference_image") if isinstance(reference, dict) else None
                    if not isinstance(name, str) or not name.startswith("characters/"):
                        raise ValueError("character reference_image không hợp lệ")
                    expected_paths.add(name)
            except (OSError, UnicodeError, ValueError) as exc:
                result.fail(f"Không thể resolve TOTAL_IMAGE_COUNT từ story.json: {exc}")
        if not isinstance(asset_results, list):
            result.fail("image_evidence.asset_results phải là array")
        else:
            paths = [row.get("path") if isinstance(row, dict) else None for row in asset_results]
            if len(paths) != len(expected_paths) or len(set(paths)) != len(paths) or set(paths) != expected_paths:
                result.fail(
                    "image_evidence.asset_results phải bind exact TOTAL_IMAGE_COUNT "
                    f"({len(expected_paths)}) ảnh, không thiếu/trùng/thừa path"
                )
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
    except (OSError, SyntaxError, UnidentifiedImageError) as exc:
        result.fail(f"{name}: ảnh không hợp lệ: {exc}")


def validate_archive(path: Path, contract: PromptContract | None = None) -> ValidationResult:
    contract = contract or load_prompt_contract()
    from studio.workflow_package import inspect_members, read_archive
    result = _result(path.name, contract)
    try:
        members = read_archive(path)
        inspection = inspect_members(members, archive=True, contract=contract)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        result.fail(f"ZIP không hợp lệ: {exc}")
        result.compatibility_mode = "UNSUPPORTED"
        return result
    result.status = inspection["status"]
    result.compatibility_mode = inspection["compatibility"]
    for item in inspection["checks"]:
        result.checks[item["check"]] = item["status"]
        if item["status"] == "FAIL":
            result.errors.append(f'{item["check"]}: {item["detail"]}')
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
    validation = path / "validation_report.json"
    if validation.is_file():
        results.append(validate_story_validation(validation, story if story.is_file() else None, contract))
    anchor = path / "series_anchor.json"
    if anchor.is_file():
        results.append(validate_series_anchor(anchor, contract))
    for archive_name in ("story_stage1.zip", "story_stage2.zip", "story.zip", "story_video_prompts.zip"):
        archive = path / archive_name
        if archive.is_file():
            results.append(validate_archive(archive, contract))
    if not results:
        result = _result(str(path), contract)
        result.fail("Không tìm thấy artifact chuẩn để kiểm tra")
        results.append(result)
    return results


__all__ = [
    "STORY_VALIDATION_FIELDS", "ValidationResult", "strict_json_bytes", "validate_archive", "validate_project",
    "validate_package_quality", "validate_series_anchor", "validate_story",
    "validate_story_validation", "validate_story_validation_bytes",
]
