from __future__ import annotations

import json
from json import JSONDecodeError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class AssetProfileContract:
    profile_name: str
    profile_dir: Path
    manifest_path: Path
    manifest: Dict[str, Any]
    cover: Optional[Path] = None
    scenes_dir: Optional[Path] = None
    bgm_dir: Optional[Path] = None
    bgm_config: Optional[Path] = None
    voice_defaults: Dict[str, str] | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "profile_dir": str(self.profile_dir),
            "manifest_path": str(self.manifest_path),
            "cover": str(self.cover) if self.cover else None,
            "scenes_dir": str(self.scenes_dir) if self.scenes_dir else None,
            "bgm_dir": str(self.bgm_dir) if self.bgm_dir else None,
            "bgm_config": str(self.bgm_config) if self.bgm_config else None,
            "voice_defaults": dict(self.voice_defaults or {}),
        }

VOICE_KEYS = (
    "vi_narrator",
    "vi_female",
    "vi_male",
    "en_narrator",
    "en_female",
    "en_male",
    "voice_narrator",
    "voice_female",
    "voice_male",
    "voice_en_narrator",
    "voice_en_female",
    "voice_en_male",
)


def normalize_profile_root(profile_root: str | Path | None, *, default_root: Path) -> Path:
    if profile_root is None:
        return default_root
    raw = str(profile_root).strip()
    if not raw:
        return default_root
    return Path(raw).expanduser().resolve()


def is_asset_profile_dir(path: Path) -> bool:
    return path.is_dir() and (path / "manifest.json").is_file()


def list_asset_profiles(profile_root: str | Path | None, *, default_root: Path) -> List[str]:
    root = normalize_profile_root(profile_root, default_root=default_root)
    if not root.exists() or not root.is_dir():
        return []
    return [child.name for child in sorted(root.iterdir()) if is_asset_profile_dir(child)]


def pick_default_asset_profile(profiles: Iterable[str], preferred: str = "demo") -> str:
    ordered = list(profiles)
    if preferred in ordered:
        return preferred
    return ""


def load_json_dict(path: Path, *, logger_warning: Optional[Callable[[str, Path, Exception | None], None]] = None) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
        if logger_warning is not None:
            logger_warning("Failed to read JSON file %s: %s", path, exc)
        return None
    if isinstance(data, dict):
        return data
    if logger_warning is not None:
        logger_warning("JSON file %s must contain an object at the top level", path, None)
    return None


def load_asset_profile_manifest(
    profile_name: str,
    profile_root: str | Path | None,
    *,
    default_root: Path,
    on_profile_missing: Callable[[Path, Path], Exception],
    on_manifest_invalid: Callable[[Path], Exception],
    logger_warning: Optional[Callable[[str, Path, Exception | None], None]] = None,
) -> Tuple[Path, Dict[str, Any]]:
    profile_dir = normalize_profile_root(profile_root, default_root=default_root) / profile_name
    manifest_path = profile_dir / "manifest.json"

    if not profile_dir.is_dir():
        raise on_profile_missing(profile_dir, manifest_path)
    if not manifest_path.is_file():
        raise on_profile_missing(profile_dir, manifest_path)

    manifest = load_json_dict(manifest_path, logger_warning=logger_warning)
    if manifest is None:
        raise on_manifest_invalid(manifest_path)
    return profile_dir, manifest


def resolve_profile_path(profile_dir: Path, value: Any) -> Optional[Path]:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p
    return (profile_dir / p).resolve()


def get_manifest_str(manifest: Dict[str, Any], key: str) -> Optional[str]:
    value = manifest.get(key)
    if isinstance(value, str):
        value = value.strip()
        if value:
            return value
    return None


def resolve_manifest_relative_path(profile_dir: Path, manifest: Dict[str, Any], key: str) -> Optional[Path]:
    value = get_manifest_str(manifest, key)
    if value is None:
        return None
    return resolve_profile_path(profile_dir, value)


def resolve_profile_voice_defaults(manifest: Dict[str, Any]) -> Dict[str, str]:
    voices = manifest.get("voices")
    if not isinstance(voices, dict):
        return {}
    resolved: Dict[str, str] = {}
    for key in VOICE_KEYS:
        val = voices.get(key)
        if isinstance(val, str) and val.strip():
            resolved[key] = val.strip()
    return resolved


def resolve_asset_profile_contract(
    profile_name: str,
    profile_root: str | Path | None,
    *,
    default_root: Path,
    on_profile_missing: Callable[[Path, Path], Exception],
    on_manifest_invalid: Callable[[Path], Exception],
    logger_warning: Optional[Callable[[str, Path, Exception | None], None]] = None,
) -> AssetProfileContract:
    profile_dir, manifest = load_asset_profile_manifest(
        profile_name,
        profile_root,
        default_root=default_root,
        on_profile_missing=on_profile_missing,
        on_manifest_invalid=on_manifest_invalid,
        logger_warning=logger_warning,
    )
    manifest_path = profile_dir / "manifest.json"
    return AssetProfileContract(
        profile_name=profile_name,
        profile_dir=profile_dir,
        manifest_path=manifest_path,
        manifest=manifest,
        cover=resolve_manifest_relative_path(profile_dir, manifest, "default_cover"),
        scenes_dir=resolve_manifest_relative_path(profile_dir, manifest, "default_scenes_dir"),
        bgm_dir=resolve_manifest_relative_path(profile_dir, manifest, "bgm_dir"),
        bgm_config=resolve_manifest_relative_path(profile_dir, manifest, "bgm_config"),
        voice_defaults=resolve_profile_voice_defaults(manifest),
    )
