from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from audio.runtime import resolve_project_root


def project_root(module_file: str | Path | None = None) -> Path:
    probe = module_file or __file__
    return resolve_project_root(probe)


def _safe_name(value: str) -> str:
    return str(value or "shared").strip().replace("\\", "_").replace("/", "_") or "shared"


_MODULE_MODEL_BRANCHES = {"audio", "story", "image", "video"}


def _branch_models_dir(root: Path, branch: str) -> Path:
    dirname = "models" if branch == "audio" else "local_models"
    return (root / branch / dirname).resolve()


def _module_models_root(module_file: str | Path | None = None) -> Path | None:
    probe = Path(module_file or __file__).resolve()
    root = project_root(probe)
    try:
        rel = probe.relative_to(root)
    except ValueError:
        return None
    if not rel.parts:
        return None
    branch = rel.parts[0]
    if branch not in _MODULE_MODEL_BRANCHES:
        return None
    return _branch_models_dir(root, branch)


def _legacy_models_root(module_file: str | Path | None = None) -> Path:
    return (project_root(module_file or __file__) / "models").resolve()



def models_root(module_file: str | Path | None = None) -> Path:
    root = _module_models_root(module_file) or _legacy_models_root(module_file)
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass(frozen=True)
class ModelStoreEntry:
    relative_path: str
    kind: str
    size_bytes: int
    file_count: int
    directory_count: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ModelStoreReport:
    root: str
    entries: tuple[ModelStoreEntry, ...]
    total_size_bytes: int = 0
    total_file_count: int = 0
    total_directory_count: int = 0

    @property
    def size_bytes(self) -> int:
        return self.total_size_bytes

    @property
    def file_count(self) -> int:
        return self.total_file_count

    @property
    def directory_count(self) -> int:
        return self.total_directory_count

    def as_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "size_bytes": self.size_bytes,
            "file_count": self.file_count,
            "directory_count": self.directory_count,
            "entries": [entry.as_dict() for entry in self.entries],
        }


def _tree_stats(path: Path) -> tuple[int, int, int]:
    if path.is_file():
        return path.stat().st_size, 1, 0
    size = 0
    files = 0
    directories = 0
    for child in path.rglob("*"):
        if child.is_dir():
            directories += 1
        elif child.is_file():
            files += 1
            size += child.stat().st_size
    return size, files, directories


def _entry_kind(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parts = rel.parts
    if not parts:
        return "root"
    if parts[0] == "_cache":
        return "cache" if len(parts) <= 2 else "cache-target"
    if len(parts) == 1:
        return "provider"
    return "model"


def _model_store_total(root: Path, *, include_cache: bool) -> tuple[int, int, int]:
    if include_cache:
        return _tree_stats(root)
    size = 0
    files = 0
    directories = 0
    for child in root.iterdir():
        if child.name == "_cache":
            continue
        child_size, child_files, child_dirs = _tree_stats(child)
        size += child_size
        files += child_files
        directories += child_dirs + (1 if child.is_dir() else 0)
    return size, files, directories


def scan_model_store(
    module_file: str | Path | None = None,
    *,
    include_cache: bool = True,
    max_depth: int = 2,
) -> ModelStoreReport:
    root = models_root(module_file)
    entries: list[ModelStoreEntry] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        rel = path.relative_to(root)
        if not include_cache and rel.parts and rel.parts[0] == "_cache":
            continue
        if len(rel.parts) > max_depth:
            continue
        size, files, directories = _tree_stats(path)
        entries.append(
            ModelStoreEntry(
                relative_path=rel.as_posix() + ("/" if path.is_dir() else ""),
                kind=_entry_kind(path, root),
                size_bytes=size,
                file_count=files,
                directory_count=directories,
            )
        )
    total_size, total_files, total_directories = _model_store_total(root, include_cache=include_cache)
    return ModelStoreReport(
        root=str(root),
        entries=tuple(entries),
        total_size_bytes=total_size,
        total_file_count=total_files,
        total_directory_count=total_directories,
    )


def format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size_bytes} B"


def prune_empty_model_directories(module_file: str | Path | None = None, *, apply: bool = False) -> list[str]:
    root = models_root(module_file)
    empty_dirs = [
        path
        for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True)
        if path.is_dir() and not any(path.iterdir())
    ]
    removed: list[str] = []
    for path in empty_dirs:
        rel = path.relative_to(root).as_posix() + "/"
        removed.append(rel)
        if apply:
            path.rmdir()
    return removed


def remove_model_store_path(relative_path: str, module_file: str | Path | None = None, *, apply: bool = False) -> Path:
    root = models_root(module_file)
    raw = str(relative_path or "").strip().strip("/\\")
    if not raw:
        raise ValueError("Model path cannot be empty.")
    target = (root / raw).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Model path must stay inside {root}.") from exc
    if not target.exists():
        raise FileNotFoundError(target)
    if apply:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    return target


def provider_models_dir(provider: str, module_file: str | Path | None = None) -> Path:
    safe = str(provider or "shared").strip().replace("\\", "_").replace("/", "_") or "shared"
    root = models_root(module_file)
    path = root if root.parent.name == safe else (root / safe).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_root(module_file: str | Path | None = None) -> Path:
    root = (models_root(module_file) / "_cache").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def provider_cache_dir(provider: str, module_file: str | Path | None = None) -> Path:
    safe = str(provider or "shared").strip().replace("\\", "_").replace("/", "_") or "shared"
    path = (cache_root(module_file) / safe).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def provider_hub_snapshots_dir(provider: str, module_file: str | Path | None = None) -> Path:
    return (provider_cache_dir(provider, module_file) / "hub").resolve()


def configure_hf_runtime(*, provider: str, module_file: str | Path | None = None, allow_network: bool = False) -> dict[str, str]:
    cache_dir = provider_cache_dir(provider, module_file)
    hub_dir = (cache_dir / "hub").resolve()
    assets_dir = (cache_dir / "assets").resolve()
    transformers_dir = (cache_dir / "transformers").resolve()
    torch_dir = (cache_root(module_file) / "torch").resolve()
    for path in (hub_dir, assets_dir, transformers_dir, torch_dir):
        path.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(cache_dir)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hub_dir)
    os.environ["HF_ASSETS_CACHE"] = str(assets_dir)
    os.environ["TRANSFORMERS_CACHE"] = str(transformers_dir)
    os.environ["TORCH_HOME"] = str(torch_dir)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if allow_network:
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)
    else:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return {
        "HF_HOME": str(cache_dir),
        "HUGGINGFACE_HUB_CACHE": str(hub_dir),
        "HF_ASSETS_CACHE": str(assets_dir),
        "TRANSFORMERS_CACHE": str(transformers_dir),
        "TORCH_HOME": str(torch_dir),
    }


def local_model_candidates(model_ref: str, *, provider: str, module_file: str | Path | None = None) -> list[Path]:
    raw = str(model_ref or "").strip()
    if not raw:
        return []
    candidates: list[Path] = []
    p = Path(raw).expanduser()
    candidates.append(p)
    provider_dir = provider_models_dir(provider, module_file)
    candidates.append((provider_dir / raw).resolve())
    candidates.append((provider_dir / raw.replace("/", "__")).resolve())
    cache_dir = provider_cache_dir(provider, module_file)
    candidates.append((cache_dir / raw).resolve())
    candidates.append((cache_dir / raw.replace("/", "__")).resolve())
    legacy_root = _legacy_models_root(module_file)
    candidates.append((legacy_root / provider / raw).resolve())
    candidates.append((legacy_root / provider / raw.replace("/", "__")).resolve())
    raw_path = Path(raw)
    raw_parts = raw_path.parts
    if len(raw_parts) >= 3 and raw_parts[0] == "models" and raw_parts[1] in _MODULE_MODEL_BRANCHES:
        candidates.append((_branch_models_dir(project_root(module_file or __file__), raw_parts[1]) / Path(*raw_parts[2:])).resolve())
    if len(raw_parts) >= 3 and raw_parts[0] in _MODULE_MODEL_BRANCHES and raw_parts[1] in {"models", "local_models"}:
        candidates.append((_branch_models_dir(project_root(module_file or __file__), raw_parts[0]) / Path(*raw_parts[2:])).resolve())
    seen: set[str] = set()
    deduped: list[Path] = []
    for item in candidates:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def resolve_model_reference(model_ref: str, *, provider: str, module_file: str | Path | None = None, allow_network: bool = False) -> tuple[str, bool]:
    raw = str(model_ref or "").strip()
    if not raw:
        raise ValueError("Model reference cannot be empty.")
    for candidate in local_model_candidates(raw, provider=provider, module_file=module_file):
        if candidate.exists():
            return str(candidate), False
    if not allow_network:
        target_dir = provider_models_dir(provider, module_file)
        raise FileNotFoundError(
            f"Model '{raw}' was not found under {target_dir}. Place the local model there or run Update with network access."
        )

    return raw, True


def list_local_models(provider: str, module_file: str | Path | None = None) -> list[str]:
    root = provider_models_dir(provider, module_file)
    items: list[str] = []
    for child in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        items.append(child.name + ("/" if child.is_dir() else ""))
    return items


def provider_target_dir(branch: str, provider_id: str, module_file: str | Path | None = None) -> Path:
    branch_dir = provider_models_dir(branch, module_file)
    target = (branch_dir / _safe_name(provider_id)).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def list_local_targets(branch: str, module_file: str | Path | None = None, *, provider_id: str | None = None, max_depth: int = 2) -> list[str]:
    root = provider_target_dir(branch, provider_id, module_file) if provider_id else provider_models_dir(branch, module_file)
    results: list[str] = []
    if not root.exists():
        return results
    for path in sorted(root.rglob('*'), key=lambda p: (not p.is_dir(), str(p).lower())):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        depth = len(rel.parts)
        if depth == 0 or depth > max_depth:
            continue
        if any(part.startswith('.') for part in rel.parts):
            continue
        label = rel.as_posix() + ('/' if path.is_dir() else '')
        results.append(label)
    return results


def _normalize_label(value: str) -> str:
    return str(value or '').strip().lower().replace('-', '_').replace(' ', '_')


def detect_image_model_type(model_ref: str, *, mode: str | None = None) -> dict[str, Any]:
    raw = str(model_ref or '').strip()
    label = _normalize_label(Path(raw).name if raw else '')
    family = 'unknown'
    variant = 'base'
    suggested_mode = str(mode or 'txt2img').strip().lower() or 'txt2img'
    provider_hint = 'stable_diffusion_local'

    if any(token in label for token in ('controlnet', 'control_net')):
        family = 'controlnet'
        variant = 'conditioning'
        suggested_mode = 'controlnet'
    elif 'inpaint' in label:
        family = 'stable-diffusion-xl' if 'xl' in label or 'sdxl' in label else 'stable-diffusion-1.x'
        variant = 'inpaint'
        suggested_mode = 'inpaint'
    elif any(token in label for token in ('sdxl', 'xl-base', 'xl_refiner', 'refiner')):
        family = 'stable-diffusion-xl'
        variant = 'refiner' if 'refiner' in label else 'base'
    elif any(token in label for token in ('sd3', 'stable-diffusion-3', 'sd35')):
        family = 'stable-diffusion-3.x'
    elif any(token in label for token in ('flux',)):
        family = 'flux-like'
        provider_hint = 'stable_diffusion_local'
    elif any(token in label for token in ('v1-5', 'sd15', 'anything-v', 'dreamshaper', 'deliberate')):
        family = 'stable-diffusion-1.x'
    elif any(token in label for token in ('v2', 'sd2')):
        family = 'stable-diffusion-2.x'

    if suggested_mode == 'txt2img' and any(token in label for token in ('img2img', 'refiner')):
        suggested_mode = 'img2img'

    return {
        'label': raw or '-',
        'family': family,
        'variant': variant,
        'suggested_mode': suggested_mode,
        'provider_hint': provider_hint,
    }
