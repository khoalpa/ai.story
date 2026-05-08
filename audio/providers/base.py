from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class VoiceChoice:
    value: str
    label: str
    lang: str
    role: str = "narrator"


@dataclass(frozen=True)
class TtsProviderDescriptor:
    provider_id: str
    label: str
    description: str
    requires_network: bool
    optional_dependency: str | None = None
    aliases: tuple[str, ...] = ()
    sort_order: int = 100
    voice_choices: Callable[[str, str], tuple[VoiceChoice, ...]] | None = None
    local_voice_notice: Callable[[str], str | None] | None = None


def normalize_provider_token(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
