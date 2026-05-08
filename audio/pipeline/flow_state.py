from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional

VoiceTag = Literal["narrator", "female", "male"]

DEFAULT_VOICE_RATE_MAP: dict[str, str] = {
    "vi_narrator": "+12%",
    "vi_female": "+14%",
    "vi_male": "+10%",
    "en_narrator": "+12%",
    "en_female": "+13%",
    "en_male": "+11%",
}


def normalize_rate_value(value: object, fallback: str = "0%") -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    if raw.endswith("%"):
        try:
            pct = float(raw[:-1])
        except Exception:
            return raw
    else:
        try:
            pct = float(raw)
        except Exception:
            return fallback
    return f"{pct:+.0f}%" if pct else "0%"


def default_rate_for_voice(voice: VoiceTag, voice_rate_map: Mapping[str, Any] | None = None, *, lang: str = "vi") -> str:
    lang_key = f"{str(lang or 'vi').strip().lower()}_{voice}"
    if voice_rate_map is not None:
        candidate = voice_rate_map.get(lang_key)
        if candidate is None:
            candidate = voice_rate_map.get(voice)
        if candidate is not None:
            return normalize_rate_value(candidate, fallback=DEFAULT_VOICE_RATE_MAP.get(lang_key, "0%"))
    return DEFAULT_VOICE_RATE_MAP.get(lang_key, DEFAULT_VOICE_RATE_MAP.get(voice, "0%"))


@dataclass
class VoiceFlowState:
    current_voice: VoiceTag = "narrator"
    current_rate: str = ""
    current_lang: str = "vi"
    voice_rate_map: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not str(self.current_rate or "").strip():
            self.current_rate = default_rate_for_voice(self.current_voice, self.voice_rate_map, lang=self.current_lang)

    def apply_tags(
        self,
        voice_tag: Optional[VoiceTag] = None,
        rate_tag: Optional[str] = None,
        lang_tag: Optional[str] = None,
    ) -> tuple[VoiceTag, str, str, bool]:
        voice_changed = False
        if voice_tag is not None:
            voice_changed = voice_tag != self.current_voice
            self.current_voice = voice_tag
        if lang_tag is not None:
            self.current_lang = lang_tag
        if rate_tag is not None:
            self.current_rate = rate_tag
        elif voice_changed or lang_tag is not None:
            self.current_rate = default_rate_for_voice(self.current_voice, self.voice_rate_map, lang=self.current_lang)
        return self.current_voice, self.current_rate, self.current_lang, (lang_tag is not None)


@dataclass
class ZoneFlowState:
    current_zone: str = "opening"

    def apply_comment(self, maybe_zone: Optional[str]) -> bool:
        if maybe_zone:
            self.current_zone = maybe_zone
            return True
        return False

    def resolve(self, line_zone: Optional[str] = None) -> str:
        if line_zone:
            self.current_zone = line_zone
        return self.current_zone


@dataclass
class EnvironmentFlowState:
    current_env: str = "none"

    def apply_comment(self, mapped_env: Optional[str]) -> bool:
        if mapped_env is None:
            return False
        self.current_env = mapped_env
        return True

    def resolve_for_line(self, detected_or_inline_env: Optional[str]) -> str:
        if detected_or_inline_env is not None:
            self.current_env = detected_or_inline_env
            return detected_or_inline_env
        return self.current_env

    def apply_explicit_env(self, env: Optional[str]) -> str:
        if env is not None:
            self.current_env = env
        return self.current_env
