#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from audio import asset_profiles as common
from audio.asset_profiles import AssetProfileContract
from audio.logging_utils import get_logger
from audio.paths import PACKAGE_PROFILE_ROOT

logger = get_logger(__name__)


def _warn(message: str, path: Path, exc: Exception | None) -> None:
    if exc is None:
        logger.warning(message, path)
    else:
        logger.warning(message, path, exc)


def _missing(profile_dir: Path, manifest_path: Path) -> Exception:
    if not profile_dir.is_dir():
        return FileNotFoundError(f"Không tìm thấy asset profile: {profile_dir}")
    return FileNotFoundError(f"Không tìm thấy manifest của asset profile: {manifest_path}")


def _invalid(manifest_path: Path) -> Exception:
    return FileNotFoundError(
        f"Không tìm thấy hoặc không đọc được manifest của asset profile: {manifest_path}"
    )


def normalize_profile_root(profile_root: str | Path | None) -> Path:
    return common.normalize_profile_root(profile_root, default_root=PACKAGE_PROFILE_ROOT)


def load_json_dict(path: Path) -> Optional[Dict[str, Any]]:
    return common.load_json_dict(path, logger_warning=_warn)


def load_asset_profile_manifest(profile_name: str, profile_root: str | Path | None) -> Tuple[Path, Dict[str, Any]]:
    return common.load_asset_profile_manifest(
        profile_name,
        profile_root,
        default_root=PACKAGE_PROFILE_ROOT,
        on_profile_missing=_missing,
        on_manifest_invalid=_invalid,
        logger_warning=_warn,
    )


def resolve_asset_profile_contract(profile_name: str, profile_root: str | Path | None) -> AssetProfileContract:
    return common.resolve_asset_profile_contract(
        profile_name,
        profile_root,
        default_root=PACKAGE_PROFILE_ROOT,
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


def resolve_profile_voice_defaults(manifest: Dict[str, Any]) -> Dict[str, str]:
    return common.resolve_profile_voice_defaults(manifest)
