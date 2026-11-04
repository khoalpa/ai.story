"""Safe JSON pretty-printing for project artifacts."""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JsonFormatResult:
    source: Path
    text: str
    original_bytes: int
    original_lines: int
    formatted_bytes: int
    formatted_lines: int


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"khóa JSON bị trùng: {key}")
        result[key] = value
    return result


def _parse_json(raw: bytes) -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("JSON có UTF-8 BOM")
    text = raw.decode("utf-8", errors="strict")

    def reject_constant(value: str) -> None:
        raise ValueError(f"hằng JSON không hữu hạn: {value}")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"số JSON không hữu hạn: {value}")
        return number

    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=reject_constant,
        parse_float=finite_float,
    )


def format_json_file(path: Path, *, indent: int = 2, newline: str = "LF") -> JsonFormatResult:
    """Read and pretty-print one UTF-8 JSON file without reordering keys."""
    source = path.expanduser().resolve()
    if source.suffix.lower() != ".json":
        raise ValueError("Chỉ hỗ trợ tệp có phần mở rộng .json")
    if indent not in (2, 4):
        raise ValueError("Indent phải là 2 hoặc 4 khoảng trắng")
    if newline not in ("LF", "CRLF"):
        raise ValueError("Kiểu xuống dòng phải là LF hoặc CRLF")

    raw = source.read_bytes()
    document = _parse_json(raw)
    text = json.dumps(document, ensure_ascii=False, indent=indent, allow_nan=False)
    text += "\n"
    if newline == "CRLF":
        text = text.replace("\n", "\r\n")
    encoded = text.encode("utf-8")
    return JsonFormatResult(
        source=source,
        text=text,
        original_bytes=len(raw),
        original_lines=len(raw.splitlines()) or 1,
        formatted_bytes=len(encoded),
        formatted_lines=len(text.splitlines()),
    )


def default_formatted_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}.formatted.json")


def existing_picker_directory(value: str | Path) -> str:
    """Return the nearest existing directory for a native file picker."""
    candidate = Path(str(value or "")).expanduser()
    if candidate.is_file():
        return str(candidate.parent)
    if candidate.is_dir():
        return str(candidate)
    for parent in candidate.parents:
        if parent.is_dir():
            return str(parent)
    return str(Path.cwd())


def choose_json_file(initial_value: str | Path) -> str | None:
    """Open the operating system's JSON file picker."""
    root = None
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            parent=root,
            initialdir=existing_picker_directory(initial_value),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Chọn tệp JSON cần làm đẹp",
        )
        return str(Path(selected).resolve()) if selected else None
    finally:
        if root is not None:
            root.destroy()


def _available_backup_path(source: Path) -> Path:
    first = source.with_suffix(source.suffix + ".bak")
    if not first.exists():
        return first
    index = 1
    while True:
        candidate = source.with_suffix(source.suffix + f".bak.{index}")
        if not candidate.exists():
            return candidate
        index += 1


def save_formatted_json(
    result: JsonFormatResult,
    destination: Path,
    *,
    overwrite_source: bool = False,
    create_backup: bool = True,
) -> tuple[Path, Path | None]:
    """Atomically save formatted JSON and optionally back up an overwritten source."""
    target = destination.expanduser().resolve()
    source = result.source.resolve()
    if target.suffix.lower() != ".json":
        raise ValueError("Tệp đích phải có phần mở rộng .json")
    if target == source and not overwrite_source:
        raise ValueError("Cần xác nhận ghi đè tệp nguồn")
    target.parent.mkdir(parents=True, exist_ok=True)

    backup: Path | None = None
    if target == source and create_backup:
        backup = _available_backup_path(source)
        shutil.copy2(source, backup)

    payload = result.text.encode("utf-8")
    handle, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise

    # Verify the exact bytes just written with the same strict parser.
    if _parse_json(target.read_bytes()) != _parse_json(payload):
        raise OSError("Nội dung xác minh sau khi lưu không khớp")
    return target, backup


__all__ = [
    "JsonFormatResult",
    "choose_json_file",
    "default_formatted_path",
    "existing_picker_directory",
    "format_json_file",
    "save_formatted_json",
]
