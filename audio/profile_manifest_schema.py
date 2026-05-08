from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from audio.logging_utils import get_logger

logger = get_logger(__name__)

PROFILE_MANIFEST_ALLOWED_KEYS = {
    "profile_id",
    "name",
    "schema_version",
    "bgm_config",
    "bgm_dir",
    "voices",
}

PROFILE_MANIFEST_FOREIGN_KEYS = {
    "default_cover",
    "default_scenes_dir",
    "video_defaults",
}

PROFILE_MANIFEST_ALLOWED_VOICE_KEYS = {
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
}


def _normalize_optional_string(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _normalize_required_string(value: Any, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _normalize_positive_int(value: Any, field_name: str, default: int = 1) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer, got {value!r}") from exc
    if number < 1:
        raise ValueError(f"{field_name} must be >= 1")
    return number


@dataclass(frozen=True)
class ProfileManifestSchema:
    profile_id: str
    schema_version: int = 1
    name: Optional[str] = None
    bgm_config: Optional[str] = None
    bgm_dir: Optional[str] = None
    voices: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        *,
        source_path: Optional[Path] = None,
        expected_profile_id: Optional[str] = None,
    ) -> "ProfileManifestSchema":
        unknown = set(raw) - PROFILE_MANIFEST_ALLOWED_KEYS - PROFILE_MANIFEST_FOREIGN_KEYS
        if unknown:
            raise ValueError(f"Manifest chứa key không hỗ trợ: {sorted(unknown)}")
        ignored = set(raw) & PROFILE_MANIFEST_FOREIGN_KEYS
        if ignored:
            logger.debug("Ignoring foreign manifest keys for render_audio: %s", sorted(ignored))

        profile_id = _normalize_required_string(raw.get("profile_id"), "profile_id")
        if expected_profile_id and profile_id != expected_profile_id:
            raise ValueError(
                f"Manifest profile_id mismatch: expected {expected_profile_id}, got {profile_id}"
            )

        voices_raw = raw.get("voices", {})
        if voices_raw in (None, ""):
            voices_raw = {}
        if not isinstance(voices_raw, Mapping):
            raise ValueError(
                f"Manifest voices phải là object: {source_path}" if source_path else "Manifest voices phải là object"
            )
        voice_unknown = set(voices_raw) - PROFILE_MANIFEST_ALLOWED_VOICE_KEYS
        if voice_unknown:
            raise ValueError(f"Manifest voices chứa key không hỗ trợ: {sorted(voice_unknown)}")
        voices: Dict[str, str] = {}
        for key, value in voices_raw.items():
            text = _normalize_optional_string(value)
            if text is None:
                raise ValueError(f"Manifest voices.{key} phải là chuỗi không rỗng")
            voices[str(key)] = text

        schema = cls(
            profile_id=profile_id,
            schema_version=_normalize_positive_int(raw.get("schema_version"), "schema_version", default=1),
            name=_normalize_optional_string(raw.get("name")),
            bgm_config=_normalize_optional_string(raw.get("bgm_config")),
            bgm_dir=_normalize_optional_string(raw.get("bgm_dir")),
            voices=voices,
        )
        if source_path is not None:
            schema.validate_asset_paths(source_path)
        return schema

    def validate_asset_paths(self, source_path: Path) -> None:
        profile_dir = source_path.parent
        if self.bgm_config is not None:
            bgm_config_path = self.resolve_bgm_config_path(profile_dir)
            if not bgm_config_path.is_file():
                raise FileNotFoundError(f"Profile bgm_config không tồn tại: {bgm_config_path}")
        if self.bgm_dir is not None:
            bgm_dir_path = self.resolve_bgm_dir_path(profile_dir)
            if not bgm_dir_path.is_dir():
                raise FileNotFoundError(f"Profile bgm dir không tồn tại: {bgm_dir_path}")

    def resolve_bgm_config_path(self, profile_dir: Path) -> Optional[Path]:
        if self.bgm_config is None:
            return None
        path = Path(self.bgm_config)
        if not path.is_absolute():
            path = (profile_dir / path).resolve()
        return path

    def resolve_bgm_dir_path(self, profile_dir: Path) -> Optional[Path]:
        if self.bgm_dir is None:
            return None
        path = Path(self.bgm_dir)
        if not path.is_absolute():
            path = (profile_dir / path).resolve()
        return path

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "profile_id": self.profile_id,
            "schema_version": self.schema_version,
        }
        if self.name is not None:
            payload["name"] = self.name
        if self.bgm_config is not None:
            payload["bgm_config"] = self.bgm_config
        if self.bgm_dir is not None:
            payload["bgm_dir"] = self.bgm_dir
        if self.voices:
            payload["voices"] = dict(self.voices)
        return payload


def load_profile_manifest_schema(path: Path, *, expected_profile_id: Optional[str] = None) -> ProfileManifestSchema:
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy manifest của asset profile: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Không đọc được manifest của asset profile: {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError(f"Manifest tại {path} phải là object")
    schema = ProfileManifestSchema.from_mapping(raw, source_path=path, expected_profile_id=expected_profile_id)
    logger.debug("Loaded profile manifest schema from %s", path)
    return schema
