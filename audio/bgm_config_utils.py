#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bgm_config_utils.py

Helpers dùng chung để load và chuẩn hóa BGM config runtime.
Giữ logic đọc config và merge defaults ra khỏi renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from audio.bgm_config_schema import BGM_ZONE_KEYS, load_bgm_config_schema, normalize_env_key
from audio.exceptions import BgmConfigError
from audio.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_ZONE_GAIN_DB = -18.0


@dataclass
class BgmRuntimeConfig:
    env_ambience_map: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    zone_bgm: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    intro_clip: Dict[str, Any] = field(default_factory=dict)
    outro_clip: Dict[str, Any] = field(default_factory=dict)

    @property
    def env_bgm_map(self) -> Dict[str, Dict[str, Any]]:
        """Backward-compatible alias for older config/tests."""
        return self.env_ambience_map

    @env_bgm_map.setter
    def env_bgm_map(self, value: Dict[str, Dict[str, Any]]) -> None:
        self.env_ambience_map = value


def _normalize_runtime_entry(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    normalized: Dict[str, Any] = {}
    file_val = entry.get('file')
    gain_val = _to_float(entry.get('gain_db'))
    fade_in_ms = _to_int(entry.get('fade_in_ms'))
    fade_out_ms = _to_int(entry.get('fade_out_ms'))
    loop_val = entry.get('loop')
    if isinstance(file_val, str) and file_val.strip():
        normalized['file'] = file_val.strip()
    if gain_val is not None:
        normalized['gain_db'] = gain_val
    if fade_in_ms is not None:
        normalized['fade_in_ms'] = fade_in_ms
    if fade_out_ms is not None:
        normalized['fade_out_ms'] = fade_out_ms
    if isinstance(loop_val, bool):
        normalized['loop'] = loop_val
    return normalized or None


def _to_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def load_bgm_config_file(path: Path) -> Optional[Dict[str, Any]]:
    """Đọc file config BGM (JSON hoặc YAML nếu có PyYAML) và chuẩn hóa qua schema."""
    if not path.is_file():
        logger.warning("BGM config file not found: %s. Runtime config will fall back to defaults.", path)
        return None

    schema = load_bgm_config_schema(path)
    return schema.to_payload()


def build_bgm_runtime_config(current: Optional[BgmRuntimeConfig], cfg: Dict[str, Any]) -> BgmRuntimeConfig:
    """Merge dict config vào state runtime hiện tại sau khi đã qua schema."""
    state = BgmRuntimeConfig(
        env_ambience_map=dict((current.env_ambience_map if current else {}) or {}),
        zone_bgm=dict((current.zone_bgm if current else {}) or {}),
        intro_clip=dict((current.intro_clip if current else {}) or {}),
        outro_clip=dict((current.outro_clip if current else {}) or {}),
    )

    env_cfg = cfg.get('env_ambience_map') or cfg.get('env_bgm_map')
    if isinstance(env_cfg, dict):
        normalized_env_map: Dict[str, Dict[str, Any]] = {}
        for raw_key, raw_entry in env_cfg.items():
            env_key = normalize_env_key(raw_key)
            entry = _normalize_runtime_entry(raw_entry)
            if env_key and entry:
                normalized_env_map[env_key] = entry
        state.env_ambience_map = normalized_env_map

    zone_cfg = cfg.get('zone_bgm')
    if isinstance(zone_cfg, dict):
        merged_zone = dict(state.zone_bgm)
        for zone_key in BGM_ZONE_KEYS:
            z = _normalize_runtime_entry(zone_cfg.get(zone_key))
            if not z:
                continue
            current_zone = dict(merged_zone.get(zone_key) or {})
            current_zone.update(z)
            merged_zone[zone_key] = current_zone
        state.zone_bgm = merged_zone

    for key in ('intro_clip', 'outro_clip'):
        clip_cfg = cfg.get(key)
        if not isinstance(clip_cfg, dict):
            continue
        current_clip = dict(getattr(state, key) or {})
        normalized_clip = _normalize_runtime_entry(clip_cfg)
        if not normalized_clip:
            continue
        current_clip.update(normalized_clip)
        setattr(state, key, current_clip)

    return state


def load_bgm_runtime_config(path: Optional[str], current: Optional[BgmRuntimeConfig] = None) -> Optional[BgmRuntimeConfig]:
    if not path:
        return current
    raw = load_bgm_config_file(Path(path))
    if not raw:
        return current
    return build_bgm_runtime_config(current, raw)
