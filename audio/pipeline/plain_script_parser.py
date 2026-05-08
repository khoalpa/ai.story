from __future__ import annotations

import re
from typing import Any, List, Mapping, Optional, Tuple, Literal

from audio.audio_story_spec import TAG_PATTERN, extract_base_token, is_legacy_unsupported_tag
from audio.pipeline.flow_state import default_rate_for_voice as _default_rate_for_voice

VoiceTag = Literal["narrator", "female", "male"]

MIN_SILENCE_MS = 200
MAX_SILENCE_MS = 20000
RATE_TAG_SLOW = "-2%"
RATE_TAG_FAST = "+2%"


def clamp_silence_ms(ms: int) -> int:
    return max(MIN_SILENCE_MS, min(MAX_SILENCE_MS, ms))


def default_rate_for_voice(voice: VoiceTag) -> str:
    return _default_rate_for_voice(voice)


def parse_float_safe(s: str) -> Optional[float]:
    try:
        return float(str(s).strip())
    except Exception:
        return None


def normalize_bgm_name(bgm: Optional[str]) -> Optional[str]:
    if bgm is None:
        return None
    bgm = str(bgm).strip()
    return bgm or None


def detect_env_from_text(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ["mưa", "rain", "raining", "rainy"]):
        return "rain"
    if any(k in t for k in ["gió", "wind", "storm", "lốc"]):
        return "wind"
    if any(k in t for k in ["quán cà phê", "cà phê", "cafe", "coffee shop", "coffeehouse"]):
        return "cafe"
    if any(k in t for k in ["rừng", "forest", "woods", "jungle"]):
        return "forest_deep_ambience"
    if any(k in t for k in ["đêm", "night", "midnight"]):
        return "night_city_soft"
    return None


def map_sfx_value_to_env(val: str, default_env: str = "none") -> str:
    v = (val or "").strip().lower()
    if not v:
        return default_env
    if "off" in v or "none" in v:
        return "none"
    if "rain_night" in v or "rain-night" in v:
        return "rain_night"
    if "forest" in v:
        return "forest_deep_ambience"
    if "night" in v and "rain" in v:
        return "night_rain_balcony"
    if "night" in v:
        return "night_city_soft"
    if "rain" in v:
        return "rain"
    if "wind" in v:
        return "wind"
    if "cafe" in v or "café" in v:
        return "cafe"
    return default_env


def parse_tags_and_text(
    raw_line: str,
    *,
    voice_rate_map: Mapping[str, Any] | None = None,
) -> Tuple[
    Optional[VoiceTag],
    Optional[str],
    Optional[str],
    Optional[float],
    Optional[int],
    str,
    Optional[str],
]:
    tags = TAG_PATTERN.findall(raw_line)
    for t in tags:
        if is_legacy_unsupported_tag(t):
            raise ValueError(f"Unsupported legacy tag found: [{t}]. Use [BGM_DB=...] instead.")
    text_clean = TAG_PATTERN.sub("", raw_line).strip()

    voice_from_tag: Optional[VoiceTag] = None
    rate_from_tag: Optional[str] = None
    bgm_from_tag: Optional[str] = None
    bgm_gain_db_from_tag: Optional[float] = None
    silence_ms: Optional[int] = None
    lang_tag: Optional[str] = None

    for t in tags:
        upper = t.strip().upper()
        base = extract_base_token(upper)

        if base in ("NARRATOR", "NAR", "MC", "DANCHUYEN"):
            voice_from_tag = "narrator"
            continue
        if base in ("F", "FEMALE", "NU"):
            voice_from_tag = "female"
            continue
        if base in ("M", "MALE", "NAM"):
            voice_from_tag = "male"
            continue

        if upper == "SLOW":
            rate_from_tag = RATE_TAG_SLOW
            continue
        if upper == "FAST":
            rate_from_tag = RATE_TAG_FAST
            continue
        if upper == "NORMAL":
            rate_from_tag = _default_rate_for_voice(voice_from_tag or "narrator", voice_rate_map, lang=lang_tag or "vi")
            continue

        if base == "RATE" or upper.startswith("RATE="):
            if "=" in t:
                _, v = t.split("=", 1)
                rate_from_tag = v.strip()
            continue

        if base == "MUSIC" or upper.startswith("MUSIC="):
            music_file = None
            dur_ms: Optional[int] = None
            if "=" in t:
                _, rest = t.split("=", 1)
                rest = rest.strip()
                if rest:
                    parts = [p.strip() for p in rest.split(";") if p.strip()]
                    if parts:
                        music_file = parts[0]
                    if len(parts) >= 2:
                        v = parts[1].lower()
                        try:
                            if v.endswith("ms"):
                                dur_ms = int(float(v[:-2]))
                            elif v.endswith("s"):
                                dur_ms = int(float(v[:-1]) * 1000)
                            else:
                                dur_ms = int(float(v))
                        except Exception:
                            dur_ms = None
            if music_file:
                bgm_from_tag = music_file
                if dur_ms is not None and not text_clean:
                    silence_ms = clamp_silence_ms(dur_ms)
            continue

        if base == "BGM" or upper.startswith("BGM=") or upper in ("BGM_OFF", "NO_BGM", "NOBGM"):
            if upper in ("BGM_OFF", "NO_BGM", "NOBGM"):
                bgm_from_tag = "OFF"
            elif "=" in t:
                _, v = t.split("=", 1)
                v = v.strip()
                bgm_from_tag = v or None
            continue

        if base in ("BGM_DB", "BGMDB") or upper.startswith("BGM_DB=") or upper.startswith("BGMDB="):
            if "=" in t:
                _, v = t.split("=", 1)
                val = parse_float_safe(v)
                if val is not None:
                    bgm_gain_db_from_tag = val
            continue

        if base in ("VOLUME", "VOL", "GAIN") or upper.startswith("VOLUME="):
            if "=" in t:
                _, v = t.split("=", 1)
                val = parse_float_safe(v)
                if val is not None:
                    bgm_gain_db_from_tag = val
            continue

        if base in ("PAUSE", "SILENCE") or upper.startswith("PAUSE=") or upper.startswith("SILENCE="):
            val = None
            if "=" in t:
                _, v = t.split("=", 1)
                v = v.strip().lower()
                try:
                    if v.endswith("ms"):
                        val = int(float(v[:-2]))
                    elif v.endswith("s"):
                        val = int(float(v[:-1]) * 1000)
                    else:
                        val = int(float(v))
                except Exception:
                    val = None
            else:
                val = 1000
            if val is not None:
                silence_ms = clamp_silence_ms(val)
            continue

        if base in ("VI", "VN"):
            lang_tag = "vi"
            continue
        if base == "EN":
            lang_tag = "en"
            continue

    return (
        voice_from_tag,
        rate_from_tag,
        bgm_from_tag,
        bgm_gain_db_from_tag,
        silence_ms,
        text_clean,
        lang_tag,
    )
