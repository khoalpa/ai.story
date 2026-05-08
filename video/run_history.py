from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

APP_DIR_NAME = ".render_video"
DEFAULT_HISTORY_FILENAME = "history.jsonl"
DEFAULT_LOGS_DIRNAME = "logs"


def get_history_dir() -> Path:
    env = os.getenv("RENDER_VIDEO_HISTORY_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / APP_DIR_NAME


def get_history_file() -> Path:
    env = os.getenv("RENDER_VIDEO_HISTORY_FILE", "").strip()
    if env:
        return Path(env).expanduser()
    return get_history_dir() / DEFAULT_HISTORY_FILENAME


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


def _build_log_file_path(timestamp: datetime, output_hint: str | None = None) -> Path:
    logs_dir = get_history_dir() / DEFAULT_LOGS_DIRNAME
    logs_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(output_hint).stem if output_hint else "render_video"
    safe_stem = (
        "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem).strip("_")
        or "render_video"
    )
    return logs_dir / f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{safe_stem}.log"


def write_run_log(*, stdout: str = "", stderr: str = "", output_hint: str | None = None) -> Path:
    timestamp = datetime.now(timezone.utc)
    log_path = _build_log_file_path(timestamp, output_hint=output_hint)
    log_path.write_text(stdout + ("\n" if stdout and stderr else "") + stderr, encoding="utf-8")
    return log_path


def append_run_history(entry: Dict[str, Any]) -> Path:
    path = get_history_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    payload = {
        "timestamp_utc": timestamp.isoformat(),
        "schema_version": 2,
        **_json_safe(entry),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return path
