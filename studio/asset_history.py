"""Local observations of image revisions, separate from canonical story packages."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

_HISTORY_LOCK = threading.Lock()


def history_path(root: Path, storage_directory: Path | None = None) -> Path:
    identity = hashlib.sha256(os.path.normcase(str(root.resolve())).encode("utf-8")).hexdigest()
    directory = storage_directory if storage_directory is not None else Path.cwd() / ".render_audio_gui"
    return directory / f"story_asset_history_{identity}.json"


def load_asset_history(root: Path, storage_directory: Path | None = None) -> dict[str, Any]:
    path = history_path(root, storage_directory)
    if not path.exists():
        return {"version": 1, "project": str(root.resolve()), "assets": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or os.path.normcase(str(data.get("project"))) != os.path.normcase(str(root.resolve())) or not isinstance(data.get("assets"), dict):
            raise ValueError("Sai định dạng hoặc thư mục dự án.")
        for value in data["assets"].values():
            if (not isinstance(value, dict) or type(value.get("revision")) is not int or value["revision"] < 0
                    or not isinstance(value.get("sha256"), str) or not isinstance(value.get("source_fingerprint"), str)
                    or not isinstance(value.get("revisions"), list) or not isinstance(value.get("last_attempt"), dict)
                    or any(not isinstance(revision, dict) for revision in value["revisions"])):
                raise ValueError("Bản ghi phiên bản không hợp lệ.")
        return data
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Không đọc được lịch sử ảnh tại {path}; giữ nguyên tệp để kiểm tra: {exc}") from exc


def content_fingerprint(root: Path, reports: Mapping[str, Any]) -> str:
    """Identify effective content, including user overrides, without claiming provenance."""
    content = {}
    for key, filename in (("story", "story.json"), ("visual_bible", "visual_plan.json")):
        value = reports.get(key)
        if not isinstance(value, Mapping) or not value:
            try:
                value = json.loads((root / filename).read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                value = None
        if isinstance(value, Mapping) and value:
            content[filename] = value
    if "story.json" not in content:
        return ""
    raw = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_asset_observations(root: Path, rows: Sequence[Mapping[str, Any]], source_fingerprint: str,
                              *, storage_directory: Path | None = None, note: str = "") -> dict[str, Any]:
    """Record an actual local inspection, never a claimed image-generation event."""
    with _HISTORY_LOCK:
        data = load_asset_history(root, storage_directory)
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            name, digest = str(row["name"]), str(row.get("sha256") or "")
            item = data["assets"].setdefault(name, {"revision": 0, "sha256": "", "source_fingerprint": "", "revisions": []})
            readable = bool(digest and row.get("dimensions"))
            if readable and digest != item["sha256"]:
                item["revision"] += 1
                item["sha256"] = digest
                item["source_fingerprint"] = source_fingerprint
                item["revisions"].append({"revision": item["revision"], "sha256": digest,
                                          "source_fingerprint": source_fingerprint, "observed_at": now})
            status = "failed" if not readable or row.get("issues") else (
                "verified" if row.get("hash_verified") and not row.get("notices") else "needs_review")
            item["last_attempt"] = {
                "operation": "local_inspection", "status": status, "at": now,
                "observed_sha256": digest, "source_fingerprint": source_fingerprint,
                "issues": list(row.get("issues") or []), "note": note.strip(),
            }
        path = history_path(root, storage_directory)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return data


def observation_status(row: Mapping[str, Any], record: Mapping[str, Any], fingerprint: str) -> str:
    if not record:
        return "Chưa ghi nhận"
    if not row.get("sha256"):
        return "Ảnh thiếu hoặc không đọc được"
    if row["sha256"] != record.get("sha256"):
        return "Ảnh đã thay đổi sau lần ghi nhận"
    if not fingerprint or not record.get("source_fingerprint"):
        return "Chưa có phiên bản nội dung để đối chiếu"
    if fingerprint != record.get("source_fingerprint"):
        return "Nội dung truyện đã đổi; cần rà soát ảnh"
    return "Khớp lần ghi nhận"
