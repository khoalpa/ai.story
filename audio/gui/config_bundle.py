from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from audio.app_config import AppConfig
from audio.profile_config import ProfileConfig


@dataclass(frozen=True)
class GuiConfigBundle:
    app: AppConfig
    profile: ProfileConfig

    def to_payload(self) -> dict[str, Any]:
        payload = self.profile.to_payload()
        payload.update(self.app.to_payload(serialize_paths=True))
        return payload

    def __getitem__(self, key: str):
        return self.to_payload()[key]

    def get(self, key: str, default=None):
        return self.to_payload().get(key, default)
