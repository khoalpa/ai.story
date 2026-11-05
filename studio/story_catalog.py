"""Build and validate a privacy-conscious catalog of Story packages."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from studio.prompt_contract import PROJECT_ROOT
from studio.story_report import _validate_story

CATALOG_VERSION = "1.0"
DEFAULT_CATALOG_ROOT = PROJECT_ROOT / "samples"
CATALOG_FILENAME = "story_catalog.json"
MAX_JSON_BYTES = 10 * 1024 * 1024
ZIP_NAMES = {"story_stage1.zip", "story_stage2.zip", "story_stage3.zip", "story.zip", "story_video_prompts.zip"}
EXCLUDED_PARTS = {".ai_story_backups", "__pycache__", "build", "dist", "tmp", "temp", "cache"}


def _json(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("story.json vượt giới hạn 10 MiB")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("story.json phải là object")
    return value


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in plain).split())


def _script_text(story: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    script = story.get("script")
    if isinstance(script, list):
        for row in script:
            if isinstance(row, Mapping):
                for key in ("text", "content", "narration", "dialogue"):
                    if isinstance(row.get(key), str):
                        chunks.append(str(row[key]))
    return " ".join(chunks)


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _excluded(path: Path, root: Path) -> bool:
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return True
    return any(part.startswith(".") or part.casefold() in EXCLUDED_PARTS for part in parts)


def _candidates(root: Path, recursive: bool) -> Iterable[Path]:
    iterator = root.rglob("*") if recursive else root.glob("*")
    for path in iterator:
        if _excluded(path, root):
            continue
        if path.is_dir() and (path / "story.json").is_file():
            yield path
        elif path.is_file() and path.name.casefold() in ZIP_NAMES:
            yield path
        if not recursive and path.is_dir():
            for child in path.iterdir():
                if child.is_file() and child.name.casefold() in ZIP_NAMES and not _excluded(child, root):
                    yield child


def _read_source(path: Path) -> tuple[bytes, dict[str, Any] | None]:
    if path.is_dir():
        raw = (path / "story.json").read_bytes()
        manifest_path = path / "workflow_manifest.json"
        return raw, _json(manifest_path.read_bytes()) if manifest_path.is_file() else None
    with zipfile.ZipFile(path) as archive:
        names = {name.replace("\\", "/"): name for name in archive.namelist()}
        story_name = next((source for normalized, source in names.items() if normalized == "story.json"), None)
        if story_name is None:
            raise ValueError("ZIP thiếu story.json ở thư mục gốc")
        raw = archive.read(story_name)
        manifest_name = next((source for normalized, source in names.items() if normalized == "workflow_manifest.json"), None)
        return raw, _json(archive.read(manifest_name)) if manifest_name else None


def _variant(path: Path, root: Path, manifest: Mapping[str, Any] | None, include_absolute_paths: bool) -> dict[str, Any]:
    value: dict[str, Any] = {
        "path": _relative(path, root),
        "kind": "directory" if path.is_dir() else "zip",
        "prompt_version": manifest.get("prompt_version") if manifest else None,
        "stage": manifest.get("stage") if manifest else None,
        "status": manifest.get("status") if manifest else None,
    }
    if include_absolute_paths:
        value["absolute_path"] = str(path.resolve())
    return value


def _story_entry(story: Mapping[str, Any], raw: bytes) -> dict[str, Any]:
    meta_value = story.get("meta")
    meta = meta_value if isinstance(meta_value, Mapping) else {}
    title = str(meta.get("title") or "")
    text = _script_text(story)
    character_values = story.get("characters")
    characters = character_values if isinstance(character_values, list) else []
    outline_values = story.get("outline")
    outline = outline_values if isinstance(outline_values, list) else []
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "catalog_id": f"story-{digest[:16]}",
        "story_sha256": digest,
        "title": title,
        "normalized_title": _normalized(title),
        "series": meta.get("series"), "episode": meta.get("episode"),
        "profile": meta.get("profile"), "age_band": meta.get("age_band"),
        "language": meta.get("language"), "genre": meta.get("genre"),
        "tone": meta.get("tone"), "tags": meta.get("tags") if isinstance(meta.get("tags"), list) else [],
        "characters": [
            {"character_id": row.get("character_id"), "name": row.get("name"), "role": row.get("role")}
            for row in characters if isinstance(row, Mapping)
        ],
        "outline_summaries": [str(row.get("summary")) for row in outline if isinstance(row, Mapping) and row.get("summary")],
        "content_signature": {
            "normalized_script_sha256": hashlib.sha256(_normalized(text).encode("utf-8")).hexdigest(),
            "script_character_count": len(text),
        },
        "package_variants": [],
    }


def scan_story_catalog(root: Path, *, recursive: bool = False, include_absolute_paths: bool = False,
                       generated_at: str | None = None) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Thư mục không tồn tại: {root}")
    stories: dict[str, dict[str, Any]] = {}
    invalid: list[dict[str, str]] = []
    for path in sorted(set(_candidates(root, recursive)), key=lambda item: str(item).casefold()):
        try:
            raw, manifest = _read_source(path)
            story = _json(raw)
            _validate_story(story)
            digest = hashlib.sha256(raw).hexdigest()
            entry = stories.setdefault(digest, _story_entry(story, raw))
            entry["package_variants"].append(_variant(path, root, manifest, include_absolute_paths))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            invalid.append({"path": _relative(path, root), "reason": str(exc)})
    entries = sorted(stories.values(), key=lambda row: (str(row["series"] or "").casefold(), row["episode"] or 0, row["title"].casefold()))
    duplicate_groups: list[dict[str, Any]] = []
    for kind, getter in (
        ("SAME_NORMALIZED_TITLE", lambda row: row["normalized_title"]),
        ("SAME_NORMALIZED_SCRIPT", lambda row: row["content_signature"]["normalized_script_sha256"]),
    ):
        groups: dict[str, list[str]] = {}
        for row in entries:
            key = getter(row)
            if key:
                groups.setdefault(key, []).append(row["catalog_id"])
        duplicate_groups.extend({"kind": kind, "key": key, "story_ids": ids} for key, ids in groups.items() if len(ids) > 1)
    variant_count = sum(len(row["package_variants"]) for row in entries)
    catalog = {
        "story_catalog_version": CATALOG_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": {"name": "ai.story", "artifact": CATALOG_FILENAME},
        "source": {"root_label": root.name, "recursive": recursive, "absolute_paths_included": include_absolute_paths},
        "summary": {"story_count": len(entries), "package_variant_count": variant_count,
                    "invalid_source_count": len(invalid), "duplicate_group_count": len(duplicate_groups)},
        "stories": entries, "invalid_sources": invalid, "duplicate_groups": duplicate_groups,
    }
    validate_story_catalog(catalog)
    return catalog


def validate_story_catalog(value: Mapping[str, Any]) -> None:
    required = {"story_catalog_version", "generated_at", "generator", "source", "summary", "stories", "invalid_sources", "duplicate_groups"}
    if set(value) != required or value.get("story_catalog_version") != CATALOG_VERSION:
        raise ValueError("Tệp không đúng định dạng story_catalog.json v1.0")
    if not all(isinstance(value.get(key), list) for key in ("stories", "invalid_sources", "duplicate_groups")):
        raise ValueError("Danh sách catalog không hợp lệ")
    if not isinstance(value.get("generator"), Mapping) or set(value["generator"]) != {"name", "artifact"}:
        raise ValueError("generator không đúng closed schema")
    if not isinstance(value.get("source"), Mapping) or set(value["source"]) != {"root_label", "recursive", "absolute_paths_included"}:
        raise ValueError("source không đúng closed schema")
    if not isinstance(value.get("summary"), Mapping) or set(value["summary"]) != {
        "story_count", "package_variant_count", "invalid_source_count", "duplicate_group_count",
    }:
        raise ValueError("summary không đúng closed schema")
    story_fields = {"catalog_id", "story_sha256", "title", "normalized_title", "series", "episode", "profile",
                    "age_band", "language", "genre", "tone", "tags", "characters", "outline_summaries",
                    "content_signature", "package_variants"}
    ids: set[str] = set()
    digest = re.compile(r"[0-9a-f]{64}")
    for story in value["stories"]:
        if (not isinstance(story, Mapping) or set(story) != story_fields
                or not isinstance(story.get("catalog_id"), str) or story["catalog_id"] in ids
                or not isinstance(story.get("story_sha256"), str) or digest.fullmatch(story["story_sha256"]) is None
                or not isinstance(story.get("title"), str) or not isinstance(story.get("normalized_title"), str)
                or not isinstance(story.get("tags"), list) or not all(isinstance(item, str) for item in story["tags"])
                or not isinstance(story.get("characters"), list)
                or not isinstance(story.get("outline_summaries"), list)
                or not all(isinstance(item, str) for item in story["outline_summaries"])
                or not isinstance(story.get("package_variants"), list) or not story["package_variants"]):
            raise ValueError("Mục stories không hợp lệ")
        ids.add(story["catalog_id"])
        signature = story.get("content_signature")
        if (not isinstance(signature, Mapping) or set(signature) != {"normalized_script_sha256", "script_character_count"}
                or not isinstance(signature.get("normalized_script_sha256"), str)
                or digest.fullmatch(signature["normalized_script_sha256"]) is None
                or type(signature.get("script_character_count")) is not int or signature["script_character_count"] < 0):
            raise ValueError("content_signature không hợp lệ")
        if any(not isinstance(row, Mapping) or set(row) != {"character_id", "name", "role"} for row in story["characters"]):
            raise ValueError("characters catalog không đúng closed schema")
        for variant in story["package_variants"]:
            path = str(variant.get("path") or "") if isinstance(variant, Mapping) else ""
            allowed = {"path", "kind", "prompt_version", "stage", "status"}
            if value["source"].get("absolute_paths_included"):
                allowed.add("absolute_path")
            if not isinstance(variant, Mapping) or set(variant) != allowed or variant.get("kind") not in {"directory", "zip"}:
                raise ValueError("package_variants không đúng closed schema")
            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("package_variants.path phải là đường dẫn tương đối an toàn")
    for row in value["invalid_sources"]:
        if not isinstance(row, Mapping) or set(row) != {"path", "reason"}:
            raise ValueError("invalid_sources không đúng closed schema")
    for row in value["duplicate_groups"]:
        if (not isinstance(row, Mapping) or set(row) != {"kind", "key", "story_ids"}
                or row.get("kind") not in {"SAME_NORMALIZED_TITLE", "SAME_NORMALIZED_SCRIPT"}
                or not isinstance(row.get("story_ids"), list) or len(row["story_ids"]) < 2
                or not set(row["story_ids"]) <= ids):
            raise ValueError("duplicate_groups không hợp lệ")
    summary = value["summary"]
    if (summary["story_count"] != len(value["stories"])
            or summary["package_variant_count"] != sum(len(row["package_variants"]) for row in value["stories"])
            or summary["invalid_source_count"] != len(value["invalid_sources"])
            or summary["duplicate_group_count"] != len(value["duplicate_groups"])):
        raise ValueError("summary không khớp dữ liệu catalog")


def catalog_bytes(catalog: Mapping[str, Any]) -> bytes:
    validate_story_catalog(catalog)
    return (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_story_catalog(catalog: Mapping[str, Any], destination: Path) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = catalog_bytes(catalog)
    handle, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


__all__ = ["CATALOG_FILENAME", "CATALOG_VERSION", "DEFAULT_CATALOG_ROOT", "catalog_bytes",
           "scan_story_catalog", "validate_story_catalog", "write_story_catalog"]
