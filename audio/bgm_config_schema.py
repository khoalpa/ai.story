from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from audio.exceptions import BgmConfigError
from audio.logging_utils import get_logger

logger = get_logger(__name__)

BGM_CONFIG_ALLOWED_KEYS = {
    "version",
    "schema_version",
    "base_dir",
    "intro_clip",
    "outro_clip",
    "zone_bgm",
    "env_ambience_map",
    "env_bgm_map",
}

BGM_ENTRY_ALLOWED_KEYS = {"file", "gain_db", "fade_in_ms", "fade_out_ms", "loop"}
BGM_ZONE_KEYS = (
    "greeting",
    "opening",
    "introduction",
    "development",
    "climax",
    "falling",
    "ending",
    "farewell",
)

ENV_KEY_ALIASES = {
    "city_soft": "night_city_soft",
    "cafe_soft": "cafe",
    "rain_soft": "rain",
    "forest": "forest_deep_ambience",
    "night_city": "night_city_soft",
    "night-rain": "night_rain_balcony",
    "night_rain": "night_rain_balcony",
    "rain-night": "rain_night",
    "hospital_roomt": "hospital_room",
}


def normalize_env_key(value: Any) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    return ENV_KEY_ALIASES.get(raw, raw)


def _to_float(value: Any, field_name: str) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as exc:
            raise BgmConfigError(f"{field_name} must be numeric, got {value!r}") from exc
    raise BgmConfigError(f"{field_name} must be numeric, got {type(value).__name__}")


def _to_non_negative_int(value: Any, field_name: str) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise BgmConfigError(f"{field_name} must be an integer number of milliseconds")
    if isinstance(value, int):
        result = value
    elif isinstance(value, float) and value.is_integer():
        result = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            result = int(text)
        except ValueError as exc:
            raise BgmConfigError(f"{field_name} must be an integer number of milliseconds, got {value!r}") from exc
    else:
        raise BgmConfigError(f"{field_name} must be an integer number of milliseconds")
    if result < 0:
        raise BgmConfigError(f"{field_name} must be >= 0")
    return result


def _to_bool(value: Any, field_name: str) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
    raise BgmConfigError(f"{field_name} must be boolean")


@dataclass(frozen=True)
class BgmAssetEntry:
    file: str
    gain_db: Optional[float] = None
    fade_in_ms: Optional[int] = None
    fade_out_ms: Optional[int] = None
    loop: Optional[bool] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, field_name: str) -> "BgmAssetEntry":
        unknown = set(raw) - BGM_ENTRY_ALLOWED_KEYS
        if unknown:
            raise BgmConfigError(f"{field_name} contains unsupported keys: {sorted(unknown)}")
        file_value = str(raw.get("file") or "").strip()
        if not file_value:
            raise BgmConfigError(f"{field_name}.file is required")
        return cls(
            file=file_value,
            gain_db=_to_float(raw.get("gain_db"), f"{field_name}.gain_db"),
            fade_in_ms=_to_non_negative_int(raw.get("fade_in_ms"), f"{field_name}.fade_in_ms"),
            fade_out_ms=_to_non_negative_int(raw.get("fade_out_ms"), f"{field_name}.fade_out_ms"),
            loop=_to_bool(raw.get("loop"), f"{field_name}.loop"),
        )

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"file": self.file}
        if self.gain_db is not None:
            payload["gain_db"] = self.gain_db
        if self.fade_in_ms is not None:
            payload["fade_in_ms"] = self.fade_in_ms
        if self.fade_out_ms is not None:
            payload["fade_out_ms"] = self.fade_out_ms
        if self.loop is not None:
            payload["loop"] = self.loop
        return payload


@dataclass(frozen=True)
class BgmConfigSchema:
    version: int = 1
    base_dir: str = "bgm"
    intro_clip: Optional[BgmAssetEntry] = None
    outro_clip: Optional[BgmAssetEntry] = None
    zone_bgm: Dict[str, BgmAssetEntry] = field(default_factory=dict)
    env_ambience_map: Dict[str, BgmAssetEntry] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, source_path: Optional[Path] = None) -> "BgmConfigSchema":
        unknown = set(raw) - BGM_CONFIG_ALLOWED_KEYS
        if unknown:
            raise BgmConfigError(f"BGM config contains unsupported keys: {sorted(unknown)}")

        version_value = raw.get("version", raw.get("schema_version", 1))
        if isinstance(version_value, bool):
            raise BgmConfigError("version must be an integer")
        try:
            version = int(version_value)
        except Exception as exc:
            raise BgmConfigError(f"version must be an integer, got {version_value!r}") from exc
        if version < 1:
            raise BgmConfigError("version must be >= 1")

        base_dir = str(raw.get("base_dir") or "bgm").strip() or "bgm"

        intro_clip = cls._parse_optional_entry(raw.get("intro_clip"), "intro_clip")
        outro_clip = cls._parse_optional_entry(raw.get("outro_clip"), "outro_clip")
        zone_bgm = cls._parse_zone_map(raw.get("zone_bgm"))
        env_ambience_map = cls._parse_env_map(raw.get("env_ambience_map") or raw.get("env_bgm_map"))

        schema = cls(
            version=version,
            base_dir=base_dir,
            intro_clip=intro_clip,
            outro_clip=outro_clip,
            zone_bgm=zone_bgm,
            env_ambience_map=env_ambience_map,
        )
        if source_path is not None:
            schema.validate_asset_paths(source_path)
        return schema

    @staticmethod
    def _parse_optional_entry(value: Any, field_name: str) -> Optional[BgmAssetEntry]:
        if value in (None, ""):
            return None
        if not isinstance(value, Mapping):
            raise BgmConfigError(f"{field_name} must be an object")
        return BgmAssetEntry.from_mapping(value, field_name=field_name)

    @staticmethod
    def _parse_zone_map(value: Any) -> Dict[str, BgmAssetEntry]:
        if value in (None, ""):
            return {}
        if not isinstance(value, Mapping):
            raise BgmConfigError("zone_bgm must be an object")
        unknown_zones = set(value) - set(BGM_ZONE_KEYS)
        if unknown_zones:
            raise BgmConfigError(f"zone_bgm contains unsupported zones: {sorted(unknown_zones)}")
        return {
            str(zone): BgmAssetEntry.from_mapping(entry, field_name=f"zone_bgm.{zone}")
            for zone, entry in value.items()
            if isinstance(entry, Mapping)
        }

    @staticmethod
    def _parse_env_map(value: Any) -> Dict[str, BgmAssetEntry]:
        if value in (None, ""):
            return {}
        if not isinstance(value, Mapping):
            raise BgmConfigError("env_ambience_map must be an object")
        normalized: Dict[str, BgmAssetEntry] = {}
        for raw_key, entry in value.items():
            env_key = normalize_env_key(raw_key)
            if not env_key:
                raise BgmConfigError("env_ambience_map contains an empty key")
            if not isinstance(entry, Mapping):
                raise BgmConfigError(f"env_ambience_map.{raw_key} must be an object")
            normalized[env_key] = BgmAssetEntry.from_mapping(entry, field_name=f"env_ambience_map.{env_key}")
        return normalized

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "version": self.version,
            "base_dir": self.base_dir,
        }
        if self.intro_clip is not None:
            payload["intro_clip"] = self.intro_clip.to_payload()
        if self.outro_clip is not None:
            payload["outro_clip"] = self.outro_clip.to_payload()
        if self.zone_bgm:
            payload["zone_bgm"] = {key: entry.to_payload() for key, entry in self.zone_bgm.items()}
        if self.env_ambience_map:
            payload["env_ambience_map"] = {key: entry.to_payload() for key, entry in self.env_ambience_map.items()}
        return payload

    def resolve_base_dir(self, source_path: Path) -> Path:
        base = Path(self.base_dir)
        if not base.is_absolute():
            base = (source_path.parent / base).resolve()
        return base

    def validate_asset_paths(self, source_path: Path) -> None:
        base_dir = self.resolve_base_dir(source_path)
        if not base_dir.is_dir():
            raise BgmConfigError(f"BGM base_dir does not exist: {base_dir}")

        for label, entry in self.iter_entries().items():
            asset_path = self.resolve_entry_path(entry, source_path)
            if not asset_path.is_file():
                raise BgmConfigError(f"{label} asset file not found: {asset_path}")

    def resolve_entry_path(self, entry: BgmAssetEntry, source_path: Path) -> Path:
        raw = Path(entry.file)
        if raw.is_absolute():
            return raw
        return self.resolve_base_dir(source_path) / raw

    def iter_entries(self) -> Dict[str, BgmAssetEntry]:
        payload: Dict[str, BgmAssetEntry] = {}
        if self.intro_clip is not None:
            payload["intro_clip"] = self.intro_clip
        if self.outro_clip is not None:
            payload["outro_clip"] = self.outro_clip
        for key, value in self.zone_bgm.items():
            payload[f"zone_bgm.{key}"] = value
        for key, value in self.env_ambience_map.items():
            payload[f"env_ambience_map.{key}"] = value
        return payload


def load_bgm_config_schema(path: Path) -> "BgmConfigSchema":
    if not path.is_file():
        raise BgmConfigError(f"BGM config file not found: {path}")
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise BgmConfigError(f"BGM config {path} requires PyYAML for YAML support") from exc
            with path.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle)
        else:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
    except BgmConfigError:
        raise
    except Exception as exc:
        raise BgmConfigError(f"Failed to read BGM config {path}: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise BgmConfigError(f"BGM config at {path} must be an object")
    schema = BgmConfigSchema.from_mapping(raw, source_path=path)
    logger.debug("Loaded BGM config schema from %s", path)
    return schema
