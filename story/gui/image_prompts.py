from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from story.image_sequence import ZONE_IMAGE_SEQUENCE

NEGATIVE_PROMPT = (
    "blurry, low quality, lowres, deformed, bad anatomy, duplicate, extra limbs, "
    "extra fingers, watermark, logo, text, subtitle, caption, frame, border"
)
PROMPT_VERSION = "story_image_prompt_v2"
SD_QUALITY_TAGS = "masterpiece, best quality, high detail, cinematic lighting, sharp focus"

ZONE_TO_OUTLINE = {
    "intro_card": "opening",
    "greeting": "greeting",
    "opening": "opening",
    "introduction": "introduction",
    "development": "development",
    "climax": "climax",
    "falling": "falling",
    "ending": "ending",
    "farewell": "farewell",
    "outro_card": "farewell",
}

OUTLINE_FALLBACK_SUMMARIES = {
    "greeting": "a welcoming host moment that introduces the mood of the story",
    "opening": "an atmospheric establishing scene that opens the story world",
    "introduction": "the main character and central situation are introduced visually",
    "development": "the story conflict grows through meaningful clues and emotional tension",
    "climax": "the most dramatic turning point of the story, high emotional intensity",
    "falling": "a quieter aftermath scene where the emotional tension begins to settle",
    "ending": "a resolved closing scene with a clear emotional conclusion",
    "farewell": "a gentle final goodbye image that closes the story",
    "overview": "a cohesive visual overview of the story world, mood, and recurring atmosphere",
}


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value or "story"


def _first_nonempty(*values: object) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_ascii_english_text(value: str) -> bool:
    return bool(value) and value.isascii()


def _english_or_fallback(value: object, fallback: str, *, force_fallback: bool = False) -> str:
    if force_fallback:
        return fallback
    text = _clean_text(value)
    return text if _is_ascii_english_text(text) else fallback


def _join_nonempty(values: list[object]) -> str:
    return " ".join(text for text in (_clean_text(value) for value in values) if text)


def _language_label(value: object) -> str:
    text = _clean_text(value).lower()
    if text in {"vi", "vie", "vietnamese", "tiếng việt", "tieng viet"}:
        return "Vietnamese"
    if text in {"en", "eng", "english"}:
        return "English"
    return _first_nonempty(value, "Vietnamese")


def _is_vietnamese_language(value: object) -> bool:
    text = _clean_text(value).lower()
    return text in {"vi", "vie", "vietnamese", "tiếng việt", "tieng viet"}


def _outline_summary(outline: dict[str, Any], outline_key: str, *, force_fallback: bool = False) -> str:
    fallback = OUTLINE_FALLBACK_SUMMARIES.get(outline_key, "a cinematic story beat with clear mood and visual continuity")
    return _english_or_fallback(outline.get(outline_key), fallback, force_fallback=force_fallback)


def _overview_summary(outline: dict[str, Any], fallback: str, *, force_fallback: bool = False) -> str:
    parts = [_outline_summary(outline, key, force_fallback=force_fallback) for key in ["greeting", "opening", "introduction", "development", "climax", "falling", "ending", "farewell"]]
    return _first_nonempty(_join_nonempty(parts), fallback)


def _common_style() -> str:
    return (
        "vertical 9:16, cinematic story illustration, strong focal subject, coherent environment, "
        "rich lighting, emotionally readable scene, no text overlay"
    )


def _standard_prompt(*, role: str, title: str, summary: str, genre: str, tone: str, audience: str, language: str, extra: str = "") -> str:
    parts = [
        SD_QUALITY_TAGS,
        _common_style(),
        role,
        f"story visual: {title}",
        f"genre: {genre}",
        f"tone: {tone}",
        f"audience: {audience}",
        f"language context: {language}",
        f"story beat: {summary}",
        extra,
        "no text, no captions, no typography, no logos, no watermark, no border, no user interface",
    ]
    return ", ".join(part for part in (_clean_text(value).strip(" ,.") for value in parts) if part)


def _prompt_payload(
    *,
    kind: str,
    slot: str,
    image_key: str,
    prompt: str,
    title: str,
    outline_key: str,
    source_summary: str,
    width: int = 832,
    height: int = 1472,
    steps: int = 30,
    cfg: float = 6.5,
) -> dict[str, Any]:
    return {
        "prompt_version": PROMPT_VERSION,
        "kind": kind,
        "slot": slot,
        "image_key": image_key,
        "title": title,
        "outline_key": outline_key,
        "source_summary": source_summary,
        "prompt": _clean_text(prompt),
        "negative_prompt": NEGATIVE_PROMPT,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "sampler_name": "dpmpp_2m",
        "scheduler": "karras",
        "seed": -1,
        "provider_payload": {"target": "stable_diffusion_comfyui"},
    }


def build_image_prompts(authoring: dict[str, Any]) -> dict[str, dict[str, Any]]:
    meta = (authoring or {}).get("meta") or {}
    outline = (authoring or {}).get("outline") or {}
    source_is_vietnamese = _is_vietnamese_language(meta.get("language"))
    title = _first_nonempty(
        _english_or_fallback(meta.get("title"), "", force_fallback=source_is_vietnamese),
        _english_or_fallback(meta.get("series"), "", force_fallback=source_is_vietnamese),
        "Untitled story",
    )
    genre = _english_or_fallback(meta.get("genre"), "dramatic story", force_fallback=source_is_vietnamese)
    tone = _english_or_fallback(meta.get("tone"), "cinematic, emotional", force_fallback=source_is_vietnamese)
    audience = _english_or_fallback(meta.get("audience"), "general audience", force_fallback=source_is_vietnamese)
    language = _language_label(meta.get("language"))

    opening_text = _first_nonempty(
        _outline_summary(outline, "opening", force_fallback=source_is_vietnamese),
        _english_or_fallback(outline.get("intro"), "an atmospheric establishing scene that opens the story world", force_fallback=source_is_vietnamese),
    )
    cover_summary = _first_nonempty(
        _outline_summary(outline, "climax", force_fallback=source_is_vietnamese),
        _outline_summary(outline, "development", force_fallback=source_is_vietnamese),
        opening_text,
    )
    overview_summary = _overview_summary(outline, cover_summary, force_fallback=source_is_vietnamese)

    prompts: dict[str, dict[str, Any]] = {
        "cover": _prompt_payload(
            kind="cover",
            slot="cover",
            image_key="cover",
            title=title,
            outline_key="climax",
            source_summary=cover_summary,
            prompt=_standard_prompt(
                role="premium cover art, poster key visual, hero composition",
                title=title,
                summary=cover_summary,
                genre=genre,
                tone=tone,
                audience=audience,
                language=language,
                extra="hero image, poster-like framing, one clear emotional hook",
            ),
            steps=32,
            cfg=6.5,
        ),
        "scene": _prompt_payload(
            kind="scene",
            slot="scene_overview",
            image_key="scene",
            title=title,
            outline_key="overview",
            source_summary=overview_summary,
            prompt=_standard_prompt(
                role="storyboard overview reference, cohesive scene concept art",
                title=title,
                summary=overview_summary,
                genre=genre,
                tone=tone,
                audience=audience,
                language=language,
                extra="wide atmospheric reference, recurring story world, consistent mood",
            ),
            steps=28,
            cfg=6.0,
        ),
        "intro": _prompt_payload(
            kind="scene",
            slot="intro",
            image_key="intro",
            title=title,
            outline_key="opening",
            source_summary=_first_nonempty(opening_text, cover_summary),
            prompt=_standard_prompt(
                role="opening scene, establishing shot",
                title=title,
                summary=_first_nonempty(opening_text, cover_summary),
                genre=genre,
                tone=tone,
                audience=audience,
                language=language,
                extra="first visual impression, atmospheric establishing composition",
            ),
        ),
    }

    for idx, zone_key in enumerate(ZONE_IMAGE_SEQUENCE, start=1):
        outline_key = ZONE_TO_OUTLINE.get(zone_key, zone_key)
        zone_summary = _first_nonempty(_outline_summary(outline, outline_key, force_fallback=source_is_vietnamese), cover_summary, overview_summary)
        zone_prompt = _standard_prompt(
            role=f"scene {idx:02d} of {len(ZONE_IMAGE_SEQUENCE):02d}, {zone_key}, cinematic keyframe",
            title=title,
            summary=zone_summary,
            genre=genre,
            tone=tone,
            audience=audience,
            language=language,
            extra="consistent story world, consistent mood, consistent lighting logic, character design continuity",
        )
        prompts[zone_key] = _prompt_payload(
            kind="scene",
            slot=zone_key,
            image_key=zone_key,
            title=title,
            outline_key=outline_key,
            source_summary=zone_summary,
            prompt=zone_prompt,
        )

    return prompts


def build_story_slug(authoring: dict[str, Any]) -> str:
    meta = (authoring or {}).get("meta") or {}
    return _slugify(_first_nonempty(meta.get("title"), meta.get("series"), "story"))


def dumps_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
