from __future__ import annotations

import importlib
import importlib.util
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence


@dataclass(frozen=True)
class ToolStatus:
    name: str
    configured: str
    resolved: Optional[str]
    version: Optional[str]
    available: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    version: str
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeDiagnosticsReport:
    python: str = field(default_factory=lambda: sys.version.split()[0])
    platform: str = field(default_factory=platform.platform)
    executable: str = field(default_factory=lambda: sys.executable)
    tools: tuple[ToolStatus, ...] = ()
    dependencies: tuple[DependencyStatus, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "python": self.python,
            "platform": self.platform,
            "executable": self.executable,
            "tools": {tool.name: tool.as_dict() for tool in self.tools},
            "dependencies": [dep.as_dict() for dep in self.dependencies],
        }

    def tool(self, name: str) -> Optional[ToolStatus]:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def dependency(self, name: str) -> Optional[DependencyStatus]:
        for dep in self.dependencies:
            if dep.name == name:
                return dep
        return None


def resolve_tool_path(path_or_name: str) -> Optional[str]:
    raw = str(path_or_name or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return str(p)
    return shutil.which(raw)


def read_tool_version(path_or_name: str) -> Optional[str]:
    resolved = resolve_tool_path(path_or_name)
    if not resolved:
        return None
    try:
        proc = subprocess.run(
            [resolved, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    lines = (proc.stdout or proc.stderr or "").splitlines()
    if not lines:
        return None
    first = lines[0].strip()
    return first or None


def describe_tool(path_or_name: str) -> str:
    resolved = resolve_tool_path(path_or_name)
    version = read_tool_version(path_or_name)
    if resolved and version:
        return f"{resolved} ({version})"
    if resolved:
        return resolved
    return f"missing: {path_or_name}"


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ValueError, ImportError):
        return name in sys.modules


def module_version(name: str) -> tuple[bool, str, str]:
    try:
        mod = importlib.import_module(name)
    except (ImportError, AttributeError, ValueError) as exc:
        return False, "missing", str(exc)
    value = getattr(mod, "__version__", None)
    return True, "unknown" if value is None else str(value), ""


def build_tool_statuses(tool_configs: Iterable[tuple[str, str]]) -> tuple[ToolStatus, ...]:
    statuses = []
    for name, configured in tool_configs:
        configured_value = str(configured or "").strip()
        resolved = resolve_tool_path(configured_value)
        statuses.append(
            ToolStatus(
                name=name,
                configured=configured_value,
                resolved=resolved,
                version=read_tool_version(configured_value),
                available=bool(resolved),
            )
        )
    return tuple(statuses)


def build_dependency_statuses(module_names: Sequence[str]) -> tuple[DependencyStatus, ...]:
    statuses = []
    for name in module_names:
        ok, version, detail = module_version(name)
        statuses.append(DependencyStatus(name=name, available=ok, version=version, detail=detail))
    return tuple(statuses)


def collect_runtime_diagnostics(
    *,
    tool_configs: Iterable[tuple[str, str]],
    dependency_modules: Sequence[str],
) -> RuntimeDiagnosticsReport:
    return RuntimeDiagnosticsReport(
        tools=build_tool_statuses(tool_configs),
        dependencies=build_dependency_statuses(dependency_modules),
    )


def format_runtime_diagnostics(report: RuntimeDiagnosticsReport) -> list[str]:
    lines: list[str] = []
    for tool in report.tools:
        if tool.available:
            suffix = f" | {tool.version}" if tool.version else ""
            lines.append(f"{tool.name}: {tool.resolved}{suffix}")
        else:
            lines.append(f"{tool.name}: missing (configured='{tool.configured or '-'}')")
    for dep in report.dependencies:
        if dep.available:
            version = f" {dep.version}" if dep.version and dep.version != 'unknown' else ""
            lines.append(f"{dep.name}: OK{version}")
        else:
            lines.append(f"{dep.name}: missing")
    return lines
