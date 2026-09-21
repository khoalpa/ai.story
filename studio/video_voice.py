"""Canonical native-voice plans and portable copy/paste prompt rendering."""
from __future__ import annotations

import hashlib
import unicodedata
from typing import Any, Mapping

VOICE_STRATEGY_FIELDS = (
    "audio_mode", "language", "preferred_locale", "preferred_accent",
    "selection_priority", "voice_profiles", "global_instructions",
)
VOICE_PROFILE_FIELDS = (
    "speaker_id", "role", "character_id", "voice_gender", "age_band", "locale",
    "accent", "provider_voice_id", "fallback_level", "selection_basis", "capability_status",
)
VOICE_PLAN_FIELDS = ("mode", "language", "segments", "allow_paraphrase", "source_text_sha256")
VOICE_SEGMENT_FIELDS = ("speaker_id", "role", "text", "emotion", "pace")

DEFAULT_PROFILES = (
    {"speaker_id": "narrator", "role": "NARRATOR", "character_id": None,
     "voice_gender": "NEUTRAL", "age_band": "ADULT", "locale": "vi-VN",
     "accent": "SOUTHERN_VIETNAMESE", "provider_voice_id": None,
     "fallback_level": "PROVIDER_DEFAULT_VI_VN",
     "selection_basis": "Warm source-faithful Vietnamese narrator",
     "capability_status": "NOT_VERIFIED"},
    {"speaker_id": "female_character", "role": "FEMALE", "character_id": "female_character",
     "voice_gender": "FEMALE", "age_band": "PRETEEN", "locale": "vi-VN",
     "accent": "SOUTHERN_VIETNAMESE", "provider_voice_id": None,
     "fallback_level": "SAME_GENDER_SOUTHERN",
     "selection_basis": "Young female character role",
     "capability_status": "NOT_VERIFIED"},
    {"speaker_id": "male_character", "role": "MALE", "character_id": "male_character",
     "voice_gender": "MALE", "age_band": "PRETEEN", "locale": "vi-VN",
     "accent": "SOUTHERN_VIETNAMESE", "provider_voice_id": None,
     "fallback_level": "SAME_GENDER_SOUTHERN",
     "selection_basis": "Young male character role",
     "capability_status": "NOT_VERIFIED"},
)


def default_voice_strategy() -> dict[str, Any]:
    return {
        "audio_mode": "NATIVE_GENERATED_VOICE",
        "language": "vi-VN",
        "preferred_locale": "vi-VN",
        "preferred_accent": "SOUTHERN_VIETNAMESE",
        "selection_priority": [
            "CHARACTER_VOICE_GENDER",
            "CHARACTER_CANONICAL_AGE_BAND",
            "SOUTHERN_VIETNAMESE_ACCENT",
        ],
        "voice_profiles": [dict(item) for item in DEFAULT_PROFILES],
        "global_instructions": [
            "Keep each speaker's vocal identity, accent, pitch, timbre, pacing, and recording character consistent across clips.",
            "Speak only the exact quoted Vietnamese text; do not translate, paraphrase, shorten, repeat, or add words.",
            "Keep ambience and foley below the voice; no music, singing, humming, subtitles, or unrelated dialogue.",
        ],
    }


def _speaker(role: Any) -> str:
    return {"NARRATOR": "narrator", "FEMALE": "female_character", "MALE": "male_character"}.get(str(role), "narrator")


def source_segments(script: list[Any], source: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    start_item, end_item = int(source["start_item_index"]), int(source["end_item_index"])
    for index in range(start_item, end_item + 1):
        item = script[index] if isinstance(script[index], dict) else {}
        tokens = str(item.get("text", "")).split()
        left = int(source["start_word_offset"]) if index == start_item else 0
        right = int(source["end_word_offset"]) if index == end_item else len(tokens)
        text = " ".join(tokens[left:right]).strip()
        if not text:
            continue
        role = str(item.get("voice") or "NARRATOR")
        segment = {"speaker_id": _speaker(role), "role": role, "text": text,
                   "emotion": "source-faithful", "pace": str(item.get("speed") or "NORMAL").lower()}
        if result and result[-1]["speaker_id"] == segment["speaker_id"]:
            result[-1]["text"] += " " + text
        else:
            result.append(segment)
    return result


def build_voice_plan(script: list[Any], source: Mapping[str, Any]) -> dict[str, Any]:
    segments = source_segments(script, source)
    joined = unicodedata.normalize("NFC", "\n".join(item["text"] for item in segments))
    roles = {item["role"] for item in segments}
    mode = "NARRATION" if roles == {"NARRATOR"} else "DIALOGUE" if "NARRATOR" not in roles else "NARRATION_AND_DIALOGUE"
    return {"mode": mode, "language": "vi-VN", "segments": segments, "allow_paraphrase": False,
            "source_text_sha256": hashlib.sha256(joined.encode("utf-8")).hexdigest()}


def native_audio_prompt(voice_plan: Mapping[str, Any], strategy: Mapping[str, Any], ambience: str) -> str:
    profiles = {p.get("speaker_id"): p for p in strategy.get("voice_profiles", []) if isinstance(p, dict)}
    lines = ["Native Vietnamese voice; keep the same speaker identity across clips."]
    for segment in voice_plan.get("segments", []):
        if not isinstance(segment, dict):
            continue
        profile = profiles.get(segment.get("speaker_id"), {})
        role = str(profile.get("role") or segment.get("role") or "speaker").replace("_", " ").title()
        lines.append(f"{role} says exactly: \"{segment.get('text', '')}\"")
    background = ambience.split(";", 1)[0].strip().rstrip(".")
    lines.extend([
        "Synchronize speech with visuals. Do not translate, paraphrase, repeat, or add words.",
        f"Background below voice: {background}. No music or extra dialogue.",
    ])
    return "\n".join(lines)


def combined_prompt(clip: Mapping[str, Any]) -> str:
    return f"VISUAL:\n{clip.get('prompt', '')}\n\n{clip.get('audio_prompt', '')}".strip()


__all__ = ["VOICE_PLAN_FIELDS", "VOICE_PROFILE_FIELDS", "VOICE_SEGMENT_FIELDS", "VOICE_STRATEGY_FIELDS", "build_voice_plan",
           "combined_prompt", "default_voice_strategy", "native_audio_prompt", "source_segments"]
