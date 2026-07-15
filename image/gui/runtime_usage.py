from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None  # type: ignore[assignment]

try:
    import torch
except Exception:  # pragma: no cover - optional runtime dependency
    torch = None  # type: ignore[assignment]


_GPU_SAMPLE_CACHE: dict[str, Any] | None = None
_GPU_SAMPLE_AT = 0.0
_GPU_SAMPLE_TTL_S = 1.0
_PROCESS = psutil.Process(os.getpid()) if psutil is not None else None
_RUNTIME_USAGE_CONTAINER: Any | None = None


def _format_bytes(value: float | int | None) -> str:
    if value is None:
        return "-"
    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(round(size))} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _sample_process_cpu_percent() -> float | None:
    if _PROCESS is None:
        return None
    try:
        return float(_PROCESS.cpu_percent(interval=None))
    except Exception:
        return None


def _sample_process_memory() -> dict[str, Any]:
    if _PROCESS is None:
        return {}
    try:
        mem = _PROCESS.memory_info()
        rss = int(getattr(mem, "rss", 0) or 0)
        vms = int(getattr(mem, "vms", 0) or 0)
        return {
            "rss_bytes": rss,
            "rss": _format_bytes(rss),
            "vms_bytes": vms,
            "vms": _format_bytes(vms),
            "process_percent": float(_PROCESS.memory_percent() or 0.0),
        }
    except Exception:
        return {}


def _sample_gpu_from_nvidia_smi() -> list[dict[str, Any]]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=False)
    except Exception:
        return []
    text = (proc.stdout or proc.stderr or "").strip()
    if not text:
        return []

    devices: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            index = int(parts[0])
        except ValueError:
            index = len(devices)
        name = parts[1]
        try:
            util = float(parts[2].rstrip("%").strip() or 0.0)
        except ValueError:
            util = 0.0
        try:
            used = float(parts[3])
        except ValueError:
            used = 0.0
        try:
            total = float(parts[4])
        except ValueError:
            total = 0.0
        devices.append(
            {
                "index": index,
                "name": name,
                "util_percent": util,
                "memory_used_mb": used,
                "memory_total_mb": total,
                "memory_used": _format_bytes(used * 1024 * 1024),
                "memory_total": _format_bytes(total * 1024 * 1024),
            }
        )
    return devices


def _sample_gpu_from_torch() -> list[dict[str, Any]]:
    if torch is None:
        return []
    try:
        if not torch.cuda.is_available():
            return []
        devices: list[dict[str, Any]] = []
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            try:
                allocated = float(torch.cuda.memory_allocated(index))
            except Exception:
                allocated = 0.0
            try:
                reserved = float(torch.cuda.memory_reserved(index))
            except Exception:
                reserved = 0.0
            total = float(getattr(props, "total_memory", 0) or 0)
            devices.append(
                {
                    "index": index,
                    "name": getattr(props, "name", f"cuda:{index}"),
                    "util_percent": None,
                    "memory_used_mb": allocated / (1024 * 1024),
                    "memory_reserved_mb": reserved / (1024 * 1024),
                    "memory_total_mb": total / (1024 * 1024),
                    "memory_used": _format_bytes(allocated),
                    "memory_reserved": _format_bytes(reserved),
                    "memory_total": _format_bytes(total),
                }
            )
        return devices
    except Exception:
        return []


def sample_gpu_usage() -> list[dict[str, Any]]:
    global _GPU_SAMPLE_CACHE, _GPU_SAMPLE_AT
    now = time.monotonic()
    if _GPU_SAMPLE_CACHE is not None and (now - _GPU_SAMPLE_AT) < _GPU_SAMPLE_TTL_S:
        return list(_GPU_SAMPLE_CACHE.get("devices") or [])

    devices = _sample_gpu_from_nvidia_smi()
    if not devices:
        devices = _sample_gpu_from_torch()

    _GPU_SAMPLE_CACHE = {"devices": devices}
    _GPU_SAMPLE_AT = now
    return list(devices)


def sample_runtime_usage() -> dict[str, Any]:
    cpu_percent = _sample_process_cpu_percent()
    memory = _sample_process_memory()
    gpus = sample_gpu_usage()

    summary: dict[str, Any] = {
        "pid": os.getpid(),
        "process_name": Path(sys.executable).name,
        "cpu_percent": cpu_percent,
        "cpu_cores": None if cpu_percent is None else round(cpu_percent / 100.0, 2),
        "memory": memory,
        "gpu_count": len(gpus),
        "gpu_devices": gpus,
        "sampled_at": time.time(),
        "cuda_available": bool(torch is not None and getattr(getattr(torch, "cuda", None), "is_available", lambda: False)()),
    }

    if gpus:
        primary = gpus[0]
        summary["gpu_primary"] = {
            "index": primary.get("index"),
            "name": primary.get("name"),
            "util_percent": primary.get("util_percent"),
            "memory_used": primary.get("memory_used"),
            "memory_total": primary.get("memory_total"),
        }
    else:
        summary["gpu_primary"] = None

    return summary


def format_runtime_usage(snapshot: dict[str, Any]) -> dict[str, Any]:
    memory = dict(snapshot.get("memory") or {})
    gpus = list(snapshot.get("gpu_devices") or [])
    cpu_percent = snapshot.get("cpu_percent")
    cuda_available = bool(snapshot.get("cuda_available"))

    if cpu_percent is None:
        cpu_label = "CPU unavailable"
    else:
        cpu_label = f"{float(cpu_percent):.1f}%"

    ram_rss = memory.get("rss") or "Unavailable"
    ram_percent = memory.get("process_percent")
    ram_label = ram_rss if ram_rss != "-" else "Unavailable"
    if isinstance(ram_percent, (int, float)) and ram_percent:
        ram_label = f"{ram_label} ({float(ram_percent):.1f}% of RAM)"

    if not gpus:
        gpu_label = "No GPU data"
    else:
        primary = gpus[0]
        name = str(primary.get("name") or f"GPU {primary.get('index', 0)}")
        util = primary.get("util_percent")
        memory_used_mb = primary.get("memory_used_mb")
        memory_total = primary.get("memory_total") or primary.get("memory_total_mb")
        gpu_label = name
        if util is not None:
            gpu_label = f"{gpu_label} | {float(util):.0f}%"
        if memory_used_mb is not None and float(memory_used_mb) > 0 and memory_total is not None:
            gpu_label = f"{gpu_label} | {primary.get('memory_used')}/{memory_total}"

    return {
        "cpu_label": cpu_label,
        "ram_label": ram_label,
        "gpu_label": gpu_label,
        "cuda_available": cuda_available,
        "snapshot": snapshot,
    }


def runtime_usage_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gpu in list(snapshot.get("gpu_devices") or []):
        rows.append(
            {
                "index": gpu.get("index"),
                "name": gpu.get("name"),
                "util_percent": gpu.get("util_percent"),
                "memory_used": gpu.get("memory_used"),
                "memory_total": gpu.get("memory_total"),
                "memory_reserved": gpu.get("memory_reserved", ""),
            }
        )
    return rows


def set_runtime_usage_container(container: Any | None) -> None:
    global _RUNTIME_USAGE_CONTAINER
    _RUNTIME_USAGE_CONTAINER = container


def _resolve_runtime_usage_container(container: Any | None = None) -> Any | None:
    if container is not None:
        return container
    return _RUNTIME_USAGE_CONTAINER


def render_runtime_usage_block(*, title: str = "Runtime usage", container: Any | None = None) -> None:
    import streamlit as st

    snapshot = sample_runtime_usage()
    rendered = format_runtime_usage(snapshot)

    if container is not None:
        with container.container():
            st.markdown(f"### {title}")
            cols = st.columns(3)
            cols[0].metric("CPU", rendered["cpu_label"])
            cols[1].metric("RAM", rendered["ram_label"])
            cols[2].metric("GPU", rendered["gpu_label"])
            rows = runtime_usage_rows(snapshot)
            if rows:
                with st.expander("GPU details", expanded=False):
                    st.dataframe(rows, width="stretch", height=min(260, 80 + 34 * len(rows)))
            st.caption("Sampling the current Python process. GPU falls back to `nvidia-smi` or `torch.cuda` when available.")
        return

    st.markdown(f"### {title}")
    cols = st.columns(3)
    cols[0].metric("CPU", rendered["cpu_label"])
    cols[1].metric("RAM", rendered["ram_label"])
    cols[2].metric("GPU", rendered["gpu_label"])

    rows = runtime_usage_rows(snapshot)
    if rows:
        with st.expander("GPU details", expanded=False):
            st.dataframe(rows, width="stretch", height=min(260, 80 + 34 * len(rows)))
    st.caption("Sampling the current Python process. GPU falls back to `nvidia-smi` or `torch.cuda` when available.")


def render_runtime_usage_compact(*, title: str = "Runtime", container: Any | None = None) -> None:
    import streamlit as st

    target = _resolve_runtime_usage_container(container)
    if target is None:
        return

    snapshot = sample_runtime_usage()
    rendered = format_runtime_usage(snapshot)
    gpus = list(snapshot.get("gpu_devices") or [])
    with target.container():
        st.markdown(f"**{title}**")
        st.text(f"CPU: {rendered['cpu_label']}")
        st.text(f"RAM: {rendered['ram_label']}")
        st.text(f"GPU: {rendered['gpu_label']}")
        if rendered.get("cuda_available") and gpus:
            primary = gpus[0]
            memory_used = primary.get("memory_used") or primary.get("memory_used_mb")
            memory_total = primary.get("memory_total") or primary.get("memory_total_mb")
            if memory_used is not None and memory_total is not None:
                st.text(f"GPU mem: {memory_used}/{memory_total}")
