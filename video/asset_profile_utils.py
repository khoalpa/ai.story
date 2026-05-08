#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from common import asset_profiles as common
from common.asset_profiles import AssetProfileContract
from video.exceptions import ProfileManifestError, ProfileNotFoundError
from video.logging_utils import get_logger
from video.paths import default_profile_root

logger = get_logger(__name__)


def _warn(message: str, path: Path, exc: Exception | None) -> None:
    if exc is None:
        logger.warning(message, path)
    else:
        logger.warning(message, path, exc)


def _missing(profile_dir: Path, manifest_path: Path) -> Exception:
    if not profile_dir.is_dir():
        return ProfileNotFoundError(f"Không tìm thấy asset profile: {profile_dir}")
    return ProfileNotFoundError(f"Không tìm thấy manifest của asset profile: {manifest_path}")


def _invalid(manifest_path: Path) -> Exception:
    return ProfileManifestError(
        f"Manifest của asset profile không hợp lệ hoặc không đọc được: {manifest_path}"
    )


def is_asset_profile_dir(path: Path) -> bool:
    return common.is_asset_profile_dir(path)


def list_asset_profiles(profile_root: str | Path | None):
    return common.list_asset_profiles(profile_root, default_root=default_profile_root())


def pick_default_asset_profile(profiles, preferred: str = "demo") -> str:
    return common.pick_default_asset_profile(profiles, preferred=preferred)


def normalize_profile_root(profile_root: str | Path | None) -> Path:
    return common.normalize_profile_root(profile_root, default_root=default_profile_root())


def load_json_dict(path: Path) -> Optional[Dict[str, Any]]:
    return common.load_json_dict(path, logger_warning=_warn)


def load_asset_profile_manifest(profile_name: str, profile_root: str | Path | None) -> Tuple[Path, Dict[str, Any]]:
    return common.load_asset_profile_manifest(
        profile_name,
        profile_root,
        default_root=default_profile_root(),
        on_profile_missing=_missing,
        on_manifest_invalid=_invalid,
        logger_warning=_warn,
    )


def resolve_asset_profile_contract(profile_name: str, profile_root: str | Path | None) -> AssetProfileContract:
    return common.resolve_asset_profile_contract(
        profile_name,
        profile_root,
        default_root=default_profile_root(),
        on_profile_missing=_missing,
        on_manifest_invalid=_invalid,
        logger_warning=_warn,
    )


def resolve_profile_path(profile_dir: Path, value: Any) -> Optional[Path]:
    return common.resolve_profile_path(profile_dir, value)


def get_manifest_str(manifest: Dict[str, Any], key: str) -> Optional[str]:
    return common.get_manifest_str(manifest, key)


def resolve_manifest_relative_path(profile_dir: Path, manifest: Dict[str, Any], key: str) -> Optional[Path]:
    return common.resolve_manifest_relative_path(profile_dir, manifest, key)


def resolve_profile_defaults(profile_root: str | Path | None, asset_profile: Optional[str]) -> Dict[str, Optional[Path]]:
    if not asset_profile:
        return {"profile_dir": None, "cover": None, "scenes_dir": None}
    contract = resolve_asset_profile_contract(asset_profile, profile_root)
    return {
        "profile_dir": contract.profile_dir,
        "cover": contract.cover,
        "scenes_dir": contract.scenes_dir,
    }


def apply_profile_runtime_defaults(*, profile_root: str | Path | None, asset_profile: Optional[str], cover: str | Path | None, scenes_dir: str | Path | None):
    defaults = resolve_profile_defaults(profile_root, asset_profile)
    resolved_cover = Path(cover).expanduser().resolve() if cover else defaults["cover"]
    resolved_scenes = Path(scenes_dir).expanduser().resolve() if scenes_dir else defaults["scenes_dir"]
    return defaults, resolved_cover, resolved_scenes


def resolve_profile_voice_defaults(manifest: Dict[str, Any]) -> Dict[str, str]:
    return common.resolve_profile_voice_defaults(manifest)
