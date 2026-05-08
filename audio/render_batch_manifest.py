from __future__ import annotations

import json
from json import JSONDecodeError
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping, Optional

from audio.render_audio_app import RenderAudioAppRequest, create_default_app_request

try:  # pragma: no cover - dependency is declared, but keep import optional in module import path
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


_REQUEST_FIELD_NAMES = {field.name for field in fields(RenderAudioAppRequest)}
_PATH_OVERRIDE_FIELDS = {"input_path", "output_dir", "profile_root", "bgmdir", "abbr_map", "bgm_config"}
_ALIAS_MAP = {
    "input": "input_path",
    "output": "output_dir",
}


@dataclass(frozen=True)
class BatchManifestJob:
    input_path: Path
    output_dir: Optional[Path] = None
    name: Optional[str] = None
    overrides: Mapping[str, Any] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_path", Path(self.input_path))
        if self.output_dir is not None:
            object.__setattr__(self, "output_dir", Path(self.output_dir))
        if self.overrides is None:
            object.__setattr__(self, "overrides", {})
        else:
            object.__setattr__(self, "overrides", dict(self.overrides))


@dataclass(frozen=True)
class BatchManifest:
    path: Path
    defaults: Mapping[str, Any]
    jobs: tuple[BatchManifestJob, ...]


class BatchManifestError(ValueError):
    pass



def load_batch_manifest(path: str | Path) -> BatchManifest:
    path = Path(path)
    payload = _load_manifest_payload(path)
    if not isinstance(payload, dict):
        raise BatchManifestError(f"Batch manifest must be a mapping: {path}")

    defaults = _normalize_overrides(dict(payload.get("defaults", {})), base_dir=path.parent, location="defaults")
    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise BatchManifestError(f"Batch manifest must define a non-empty jobs list: {path}")

    jobs: list[BatchManifestJob] = []
    for index, raw_job in enumerate(raw_jobs, start=1):
        if not isinstance(raw_job, dict):
            raise BatchManifestError(f"Job #{index} must be a mapping")
        normalized = _normalize_overrides(dict(raw_job), base_dir=path.parent, location=f"jobs[{index}]")
        input_path = normalized.pop("input_path", None)
        if input_path is None:
            raise BatchManifestError(f"jobs[{index}] is missing required field: input")
        output_dir = normalized.pop("output_dir", None)
        name = normalized.pop("name", None)
        jobs.append(BatchManifestJob(input_path=input_path, output_dir=output_dir, name=name, overrides=normalized))

    return BatchManifest(path=path, defaults=defaults, jobs=tuple(jobs))



def build_request_from_manifest_job(
    job: BatchManifestJob,
    *,
    defaults: Mapping[str, Any] | None = None,
    template: RenderAudioAppRequest | None = None,
) -> RenderAudioAppRequest:
    defaults = dict(defaults or {})
    base_input = Path(defaults.get("input_path", job.input_path))
    base_output = Path(defaults.get("output_dir", job.output_dir or job.input_path.parent / "output"))
    request = template or create_default_app_request(input_path=base_input, output_dir=base_output)

    request_payload = request.to_payload()
    request_payload.update(defaults)
    request_payload.update(job.overrides)
    request_payload["input_path"] = job.input_path
    if job.output_dir is not None:
        request_payload["output_dir"] = job.output_dir

    missing = [name for name in ("input_path", "output_dir") if request_payload.get(name) is None]
    if missing:
        raise BatchManifestError(f"Manifest job {job.name or job.input_path} is missing required request fields: {', '.join(missing)}")

    return RenderAudioAppRequest.from_mapping(request_payload)



def _load_manifest_payload(path: Path) -> Any:
    suffix = path.suffix.lower()
    raw_text = path.read_text(encoding="utf-8-sig")
    if not raw_text.strip():
        raise BatchManifestError(f"Batch manifest is empty: {path}")

    if suffix == ".json":
        try:
            return json.loads(raw_text)
        except JSONDecodeError as exc:
            raise BatchManifestError(
                f"Invalid JSON batch manifest at {path}:{exc.lineno}:{exc.colno} - {exc.msg}"
            ) from exc

    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise BatchManifestError("YAML manifest support requires PyYAML")
        try:
            payload = yaml.safe_load(raw_text)
        except Exception as exc:
            raise BatchManifestError(f"Invalid YAML batch manifest at {path}: {exc}") from exc
        if payload is None:
            raise BatchManifestError(f"Batch manifest is empty: {path}")
        return payload

    raise BatchManifestError(f"Unsupported batch manifest format: {path}")



def _normalize_overrides(raw: Mapping[str, Any], *, base_dir: Path, location: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        canonical_key = _ALIAS_MAP.get(key, key)
        if canonical_key == "name":
            normalized[canonical_key] = value
            continue
        if canonical_key not in _REQUEST_FIELD_NAMES:
            raise BatchManifestError(f"Unsupported field in {location}: {key}")
        normalized[canonical_key] = _normalize_value(canonical_key, value, base_dir=base_dir)
    return normalized



def _normalize_value(key: str, value: Any, *, base_dir: Path) -> Any:
    if value is None:
        return None
    if key in _PATH_OVERRIDE_FIELDS:
        path_value = Path(value)
        return path_value if path_value.is_absolute() else base_dir / path_value
    return value
