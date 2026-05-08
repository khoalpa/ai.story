from __future__ import annotations

import io
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple


def setup_stdio() -> None:
    """Best-effort UTF-8 stdio setup for CLI tools."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
            continue
        except (AttributeError, ValueError, OSError):
            pass

        buffer = getattr(stream, "buffer", None)
        if buffer is None:
            continue

        try:
            wrapped = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")
            setattr(sys, name, wrapped)
        except (AttributeError, ValueError, OSError):
            pass


@dataclass
class UsedFilesTracker:
    """Collect and print files/directories touched by a CLI execution."""

    entries: List[Tuple[str, str]] = field(default_factory=list)
    _seen: Set[Tuple[str, str]] = field(default_factory=set)

    def add(self, label: str, path: Optional[str | Path]) -> None:
        if path is None:
            return
        self._add_resolved(label, Path(path))

    def add_many(self, label: str, paths: Iterable[str | Path]) -> None:
        for path in paths:
            self.add(label, path)

    def note(self, label: str, value: Optional[str]) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        item = (label, text)
        if item not in self._seen:
            self._seen.add(item)
            self.entries.append(item)

    def _add_resolved(self, label: str, path: Path) -> None:
        try:
            text = str(path.resolve())
        except OSError:
            text = str(path)
        item = (label, text)
        if item not in self._seen:
            self._seen.add(item)
            self.entries.append(item)

    def print_summary(self, title: str = "Các tệp/thư mục đã dùng") -> None:
        if not self.entries:
            return
        print(f"\n=== {title} ===")
        for label, value in self.entries:
            print(f"- {label}: {value}")
