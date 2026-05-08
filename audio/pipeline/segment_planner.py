from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple

from audio.bgm_config_utils import BgmRuntimeConfig
from audio.pipeline.flow_state import EnvironmentFlowState, VoiceFlowState, default_rate_for_voice as _default_rate_for_voice

VoiceTag = Literal["narrator", "female", "male"]

MIN_SILENCE_MS = 200
MAX_SILENCE_MS = 20000

TONE_PRESET_NONE = "none"
TONE_PRESET_PODCAST_TIKTOK = "podcast_tiktok"


@dataclass
class Segment:
    text: str
    voice: VoiceTag
    rate: str
    bgm: Optional[str] = None
    bgm_gain_db: Optional[float] = None
    ambience: Optional[str] = None
    ambience_gain_db: Optional[float] = None
    pause_ms_before: int = 0
    zone: str = "opening"
    lang: str = "vi"
    lang_from_tag: bool = False
    emotion: str = "neutral"
    env: str = "none"


def clamp_silence_ms(ms: int) -> int:
    return max(MIN_SILENCE_MS, min(MAX_SILENCE_MS, ms))


def default_rate_for_voice(voice: VoiceTag, voice_rate_map: Mapping[str, Any] | None = None, *, lang: str = "vi") -> str:
    return _default_rate_for_voice(voice, voice_rate_map, lang=lang)


def expand_silence_segments(classified_lines: List[dict]) -> List[dict]:
    expanded = []
    for item in classified_lines:
        text = item["text"]
        zone = item["zone"]
        silence_ms = item.get("silence_ms")
        env = item.get("env", "none")
        if silence_ms is not None:
            silence_ms = clamp_silence_ms(silence_ms)
            if text:
                expanded.append({**item, "silence_ms": None})
                expanded.append(
                    {
                        "text": "",
                        "zone": zone,
                        "is_silence_only": True,
                        "lang_tag": item.get("lang_tag"),
                        "silence_ms": silence_ms,
                    }
                )
            else:
                expanded.append(
                    {
                        "text": "",
                        "zone": zone,
                        "is_silence_only": True,
                        "lang_tag": item.get("lang_tag"),
                        "silence_ms": silence_ms,
                        "bgm_tag": item.get("bgm_tag"),
                        "bgm_db_tag": item.get("bgm_db_tag"),
                        "env": env,
                    }
                )
        else:
            expanded.append(item)
    return expanded


def assign_segments(expanded_lines: List[dict], *, voice_rate_map: Mapping[str, Any] | None = None) -> List[Segment]:
    segments: List[Segment] = []
    voice_flow = VoiceFlowState(voice_rate_map=voice_rate_map)
    env_flow = EnvironmentFlowState()
    current_bgm: Optional[str] = None
    current_bgm_gain_db: Optional[float] = None

    for item in expanded_lines:
        text = item.get("text", "")
        zone = item.get("zone", "opening")
        current_env = env_flow.apply_explicit_env(item.get("env"))

        if item.get("is_silence_only"):
            silence_ms = clamp_silence_ms(int(item.get("silence_ms") or 1000))
            seg = Segment(
                text="",
                voice=voice_flow.current_voice,
                rate=voice_flow.current_rate,
                bgm=item.get("bgm_tag"),
                bgm_gain_db=item.get("bgm_db_tag"),
                ambience=None,
                ambience_gain_db=None,
                pause_ms_before=silence_ms,
                zone=zone,
                lang=voice_flow.current_lang,
                lang_from_tag=False,
                env=current_env,
            )
            segments.append(seg)
            continue

        voice, rate, lang, lang_from_tag = voice_flow.apply_tags(
            voice_tag=item.get("voice_tag"),
            rate_tag=item.get("rate_tag"),
            lang_tag=item.get("lang_tag"),
        )

        bgm_from_tag = item.get("bgm_tag")
        if bgm_from_tag is not None:
            if str(bgm_from_tag).upper() in ("OFF", "NONE", "NO_BGM", "NOBGM", "BGM_OFF"):
                current_bgm = None
            else:
                current_bgm = bgm_from_tag

        bgm_gain_db_from_tag = item.get("bgm_db_tag")
        if bgm_gain_db_from_tag is not None:
            current_bgm_gain_db = bgm_gain_db_from_tag

        segments.append(
            Segment(
                text=text,
                voice=voice,
                rate=rate,
                bgm=current_bgm,
                bgm_gain_db=current_bgm_gain_db,
                ambience=None,
                ambience_gain_db=None,
                pause_ms_before=0,
                zone=zone,
                lang=lang,
                lang_from_tag=lang_from_tag,
                env=current_env,
            )
        )

    return segments


def auto_assign_bgm_for_zones(
    segments: List[Segment],
    main_bgm: Optional[str],
    runtime_config: Optional[BgmRuntimeConfig] = None,
) -> None:
    env_map: Dict[str, Dict[str, object]] = dict((runtime_config.env_ambience_map if runtime_config else {}) or {})
    zone_bgm: Dict[str, Dict[str, object]] = dict((runtime_config.zone_bgm if runtime_config else {}) or {})

    for seg in segments:
        if seg.bgm is None:
            zone_cfg = dict(zone_bgm.get(seg.zone) or {})
            file_name = str(zone_cfg.get("file") or "").strip()
            if file_name:
                seg.bgm = file_name
                if seg.bgm_gain_db is None:
                    try:
                        seg.bgm_gain_db = float(zone_cfg.get("gain_db", -18.0))
                    except (TypeError, ValueError):
                        seg.bgm_gain_db = -18.0
            elif main_bgm:
                seg.bgm = main_bgm

        env_cfg = env_map.get(seg.env)
        if env_cfg and seg.ambience is None:
            file_name = str(env_cfg.get("file") or "").strip()
            if file_name:
                seg.ambience = file_name
                if seg.ambience_gain_db is None:
                    try:
                        seg.ambience_gain_db = float(env_cfg.get("gain_db", -24.0))
                    except (TypeError, ValueError):
                        seg.ambience_gain_db = -24.0


def simple_sentiment(text: str) -> Tuple[str, float]:
    text_l = (text or "").lower()
    sad_words = ["sad", "buồn", "cry", "khóc", "lonely", "cô đơn", "lost", "mất"]
    tense_words = ["panic", "hoảng", "run", "chạy", "danger", "nguy hiểm", "fear", "sợ", "căng thẳng", "lo lắng", "stress"]
    happy_words = ["happy", "vui", "smile", "cười", "joy", "hạnh phúc", "warm"]

    def score(words: List[str]) -> int:
        return sum(1 for w in words if w in text_l)

    sad = score(sad_words)
    tense = score(tense_words)
    happy = score(happy_words)
    total = sad + tense + happy
    if total <= 0:
        return "neutral", 0.0
    best = max((sad, "sad"), (tense, "tense"), (happy, "happy"), key=lambda x: x[0])
    return best[1], min(1.0, best[0] / 3.0)


def apply_sentiment_tone(
    segments: List[Segment],
    *,
    voice_rate_map: Mapping[str, Any] | None = None,
    max_extra_slow: float = 0.02,
    max_extra_fast: float = 0.02,
) -> None:
    for seg in segments:
        clean_text = seg.text.strip("-–—*_ .·").strip()
        if not clean_text:
            continue
        default_rate = default_rate_for_voice(seg.voice, voice_rate_map, lang=seg.lang)
        if seg.rate != default_rate:
            continue
        label, strength = simple_sentiment(clean_text)
        seg.emotion = label
        if strength < 0.2:
            continue
        if label == "sad":
            delta = -max_extra_slow * strength
        elif label == "tense":
            delta = +max_extra_fast * strength
        elif label == "happy":
            delta = +max_extra_fast * (strength * 0.7)
        else:
            delta = 0.0
        if delta == 0.0:
            continue
        old_rate = seg.rate.strip()
        base_pct = 0.0
        if old_rate.endswith("%"):
            try:
                base_pct = float(old_rate[:-1]) / 100.0
            except Exception:
                base_pct = 0.0
        new_pct = max(-0.30, min(0.30, base_pct + delta))
        seg.rate = f"{new_pct * 100:+.0f}%"
        if label == "sad" and seg.voice == "male":
            seg.voice = "narrator"
        elif label == "happy" and seg.voice == "narrator":
            seg.voice = "female"
        elif label == "tense" and seg.voice == "narrator":
            seg.voice = "male"


def apply_podcast_tiktok_tone(segments: List[Segment]) -> None:
    """Apply a stable short-form podcast pacing preset for TikTok-style narration.

    Goals:
    - keep narrator/female/male choices stable
    - add a slightly faster base pace for short-form content
    - only nudge rate lightly by sentiment, avoiding dramatic swings
    """
    for i, seg in enumerate(segments):
        clean_text = seg.text.strip("-–—*_ .·").strip()
        if not clean_text:
            continue

        if seg.voice == "narrator":
            base_pct = 0.15
        elif seg.voice == "female":
            base_pct = 0.13
        else:
            base_pct = 0.11

        if i < 2:
            base_pct += 0.01

        label, strength = simple_sentiment(clean_text)
        seg.emotion = label

        delta = 0.0
        strength = max(0.0, min(1.0, float(strength)))
        if label == "sad":
            delta = -0.02 * max(0.5, strength)
        elif label == "tense":
            delta = 0.02 * max(0.5, strength)
        elif label == "happy":
            delta = 0.01 * max(0.5, strength)

        final_pct = max(-0.05, min(0.18, base_pct + delta))
        seg.rate = f"{final_pct * 100:+.0f}%"


def base_chars_per_second_for_voice(voice: VoiceTag) -> float:
    if voice == "narrator":
        return 14.5
    if voice == "female":
        return 15.5
    if voice == "male":
        return 13.5
    return 14.0


def rate_str_to_factor(rate: str | None) -> float:
    raw = (rate or "").strip()
    if not raw:
        return 1.0
    if raw.endswith("%"):
        try:
            return 1.0 + (float(raw[:-1]) / 100.0)
        except Exception:
            return 1.0
    try:
        return float(raw)
    except Exception:
        return 1.0
