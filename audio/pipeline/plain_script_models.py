from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

LineKind = Literal["content", "zone_comment", "env_comment"]


@dataclass(frozen=True)
class ParsedScriptLine:
    raw: str
    text: str
    kind: LineKind = "content"
    voice_tag: Optional[str] = None
    rate_tag: Optional[str] = None
    bgm_tag: Optional[str] = None
    bgm_db_tag: Optional[float] = None
    lang_tag: Optional[str] = None
    silence_ms: Optional[int] = None
    zone_hint: Optional[str] = None
    env_hint: Optional[str] = None


@dataclass(frozen=True)
class ResolvedScriptLine:
    raw: str
    text: str
    zone: str
    env: str
    voice_tag: Optional[str] = None
    rate_tag: Optional[str] = None
    bgm_tag: Optional[str] = None
    bgm_db_tag: Optional[float] = None
    lang_tag: Optional[str] = None
    silence_ms: Optional[int] = None
